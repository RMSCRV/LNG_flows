"""
Phase 6: dashboard compute pipeline.

Wraps src/'s simulator + netback + optimization modules into two cached
steps (expensive Monte Carlo simulation, done once) and one cheap step
(re-solve the LP under whatever shocks the sidebar currently specifies,
done on every "Apply Shock"). Nothing here re-derives economics that
src/ doesn't already implement -- this only wires shock inputs from
Streamlit widgets into the override functions optimization.py and
network_config.py already expose.
"""

import csv
import json
import os
import sys

import numpy as np
import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from netback import CostAssumptions
from network_config import (
    DESTINATIONS,
    ORIGINS,
    ROUTES,
    VESSEL,
    with_destination_overrides,
    with_origin_overrides,
    with_route_overrides,
    with_vessel_overrides,
)
from optimization import (
    capacity_utilization,
    evaluate_portfolio,
    portfolio_stats,
    scenario_netbacks,
    solve_cvar_lp,
    solve_ev_lp,
)
from simulator import HubParams, simulate_paths

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "processed")
N_SCENARIOS = 1000  # fewer than Phase 3/5's 2000 -- traded for interactive responsiveness
SEED = 7  # same seed as Phase 3/5, so the dashboard's baseline matches their numbers


@st.cache_data
def load_calibration():
    with open(os.path.join(DATA_DIR, "calibration", "hub_params.json")) as f:
        calibration = json.load(f)
    hub_order = calibration["correlation"]["hub_order"]
    corr_matrix = calibration["correlation"]["matrix"]
    params = [HubParams(**calibration["primary"][name]) for name in hub_order]

    with open(os.path.join(DATA_DIR, "combined", "monthly_aligned.csv")) as f:
        rows = list(csv.DictReader(f))
    latest = rows[-1]
    start_prices = {
        "HENRY_HUB": float(latest["henry_hub"]),
        "TTF": float(latest["ttf"]),
        "JKM": float(latest["jkm"]),
        "FREIGHT_ATLANTIC": float(latest["freight_atlantic"]),
        "FREIGHT_PACIFIC": float(latest["freight_pacific"]),
    }
    return hub_order, params, corr_matrix, start_prices


@st.cache_data
def baseline_scenarios():
    """N_SCENARIOS one-month-ahead scenarios from the calibrated model, unshocked."""
    hub_order, params, corr_matrix, start_prices = load_calibration()
    paths = simulate_paths(params, corr_matrix, n_paths=N_SCENARIOS, n_steps=1, start_prices=start_prices, seed=SEED)
    scenario_prices = [
        {"HENRY_HUB": paths["HENRY_HUB"][i, -1], "TTF": paths["TTF"][i, -1], "JKM": paths["JKM"][i, -1]}
        for i in range(N_SCENARIOS)
    ]
    scenario_freight = [
        {"FREIGHT_ATLANTIC": paths["FREIGHT_ATLANTIC"][i, -1], "FREIGHT_PACIFIC": paths["FREIGHT_PACIFIC"][i, -1]}
        for i in range(N_SCENARIOS)
    ]
    return scenario_prices, scenario_freight


def default_shock_params() -> dict:
    """The "no shock" state -- every multiplier 1.0, every capacity at its baseline value."""
    return {
        "ttf_mult": 1.0,
        "jkm_mult": 1.0,
        "freight_atlantic_mult": 1.0,
        "freight_pacific_mult": 1.0,
        "liquefaction_pct": {k: 100.0 for k in ORIGINS},
        "min_supply_pct": {k: 100.0 for k in ORIGINS},
        "storage_pct": {k: 100.0 for k in DESTINATIONS},
        "vessel_pct": 100.0,
        "suez_extra_days": 0.0,
        "panama_extra_days": 0.0,
        "risk_lambda": 2.0,
        "duration_months": 1,
    }


def _apply_price_shock(scenario_list: list[dict], hub: str, multiplier: float) -> list[dict]:
    if multiplier == 1.0:
        return scenario_list
    return [{**s, hub: s[hub] * multiplier} for s in scenario_list]


def build_shocked_network(shocks: dict):
    """Turn UI shock params into the override objects optimization.py's functions accept."""
    origins = with_origin_overrides(
        liquefaction={k: cfg.liquefaction_capacity_cargoes_per_month * shocks["liquefaction_pct"][k] / 100.0 for k, cfg in ORIGINS.items()},
        min_supply={k: cfg.min_supply_cargoes_per_month * shocks["min_supply_pct"][k] / 100.0 for k, cfg in ORIGINS.items()},
    )
    destinations = with_destination_overrides(
        {k: cfg.storage_capacity_cargoes * shocks["storage_pct"][k] / 100.0 for k, cfg in DESTINATIONS.items()}
    )
    vessel = with_vessel_overrides(VESSEL["fleet_size_vessels"] * shocks["vessel_pct"] / 100.0)

    route_overrides = {}
    if shocks["suez_extra_days"] > 0:
        base = next(r for r in ROUTES if r.origin == "QATAR" and r.destination == "EUROPE").transit_days
        route_overrides[("QATAR", "EUROPE")] = base + shocks["suez_extra_days"]
    if shocks["panama_extra_days"] > 0:
        base = next(r for r in ROUTES if r.origin == "US_GC" and r.destination == "ASIA").transit_days
        route_overrides[("US_GC", "ASIA")] = base + shocks["panama_extra_days"]
    routes = with_route_overrides(route_overrides) if route_overrides else ROUTES

    return origins, destinations, vessel, routes


def run_scenario(shocks: dict) -> dict:
    """
    Apply `shocks` to the baseline scenarios and network, re-solve both
    LPs, and return everything the UI needs to render. If a shock
    combination is infeasible (e.g. a take-or-pay floor left above a
    shocked-down liquefaction cap), status will say so instead of
    silently handing back a meaningless allocation -- see
    optimization.solve_ev_lp's docstring.
    """
    scenario_prices, scenario_freight = baseline_scenarios()
    scenario_prices = _apply_price_shock(scenario_prices, "TTF", shocks["ttf_mult"])
    scenario_prices = _apply_price_shock(scenario_prices, "JKM", shocks["jkm_mult"])
    scenario_freight = _apply_price_shock(scenario_freight, "FREIGHT_ATLANTIC", shocks["freight_atlantic_mult"])
    scenario_freight = _apply_price_shock(scenario_freight, "FREIGHT_PACIFIC", shocks["freight_pacific_mult"])

    origins, destinations, vessel, routes = build_shocked_network(shocks)
    assumptions = CostAssumptions()

    netbacks = scenario_netbacks(scenario_prices, scenario_freight, assumptions, routes)
    kwargs = dict(assumptions=assumptions, routes=routes, origins=origins, destinations=destinations, vessel=vessel)

    ev_alloc, ev_obj, ev_status = solve_ev_lp(netbacks, **kwargs)
    risk_alloc, risk_obj, risk_status = solve_cvar_lp(netbacks, risk_lambda=shocks["risk_lambda"], **kwargs)

    result = {
        "netbacks": netbacks,
        "routes": routes,
        "origins": origins,
        "destinations": destinations,
        "vessel": vessel,
        "ev_status": ev_status,
        "risk_status": risk_status,
        "ev_allocation": ev_alloc if ev_status == "Optimal" else None,
        "risk_allocation": risk_alloc if risk_status == "Optimal" else None,
    }

    if ev_status == "Optimal":
        cargo_size = VESSEL["cargo_size_mmbtu"]
        pv = evaluate_portfolio(ev_alloc, netbacks)
        result["ev_stats"] = portfolio_stats(pv, cargo_size_mmbtu=cargo_size)
        result["ev_utilization"] = capacity_utilization(ev_alloc, assumptions, routes, origins, destinations, vessel)
    if risk_status == "Optimal":
        cargo_size = VESSEL["cargo_size_mmbtu"]
        pv_risk = evaluate_portfolio(risk_alloc, netbacks)
        result["risk_stats"] = portfolio_stats(pv_risk, cargo_size_mmbtu=cargo_size)
        result["risk_utilization"] = capacity_utilization(risk_alloc, assumptions, routes, origins, destinations, vessel)

    return result
