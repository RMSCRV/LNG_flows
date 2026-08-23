"""
Phase 3: optimization engine.

Three strategies solving the same one-period cargo allocation problem --
how many cargoes to ship from each origin to each destination for the
month ahead -- given N price/freight scenarios from Phase 1's simulator
and the network's capacity constraints (liquefaction, storage, vessel
fleet):

- naive_allocation(): always ship to the destination with the higher
  *headline* price, ignoring capacity entirely -- that's what makes it
  naive. Feasibility against capacity is checked separately
  (clip_to_capacity()), not assumed.
- solve_ev_lp(): maximize expected netback subject to capacity. A plain
  LP -- the scenario-mean netback is the objective coefficient, so this
  needs only the scenario *mean*, not the full distribution (netback is
  affine in prices, so E[netback(prices)] = netback(E[prices]) exactly).
- solve_cvar_lp(): maximize E[netback] - risk_lambda * CVaR_alpha(loss).
  CVaR via the standard Rockafellar-Uryasev LP formulation (auxiliary
  variables zeta, u_s) -- kept as a true LP rather than a variance
  penalty, which would require a quadratic objective PuLP doesn't
  support. This is the one strategy that genuinely needs the full
  scenario distribution, not just its mean.

Both LP variants also enforce each origin's approximate take-or-pay
minimum (network_config.Origin.min_supply_cargoes_per_month, 0 for a
fully-discretionary origin) -- a lower bound on top of the usual
liquefaction/storage/vessel upper bounds, so an origin can be forced to
accept a currently-low-netback destination rather than simply shipping
nothing. naive_allocation() ignores it, same as it ignores every other
capacity constraint; that asymmetry is what makes it naive.

Every function that reads capacity takes optional origins/destinations/
vessel overrides (default to the real network's ORIGINS/DESTINATIONS/
VESSEL), mirroring the existing `routes` override -- see
network_config.with_origin_overrides() etc. This is what lets the
dashboard "shock" a capacity (e.g. Europe storage, the vessel fleet)
without mutating global state.

All three variants operate on the same units as netback.py's output
(USD/MMBtu per cargo-equivalent unit); multiply by
network_config.VESSEL["cargo_size_mmbtu"] to get total USD when
reporting portfolio value.
"""

import numpy as np
import pulp

from netback import CostAssumptions, compute_netback, destination_price_usd_per_mmbtu
from network_config import DESTINATIONS, ORIGINS, ROUTES, VESSEL, Route

DAYS_IN_PERIOD = 30.0


def scenario_netbacks(
    scenario_prices: list[dict],
    scenario_freight: list[dict],
    assumptions: CostAssumptions = CostAssumptions(),
    routes: list[Route] = ROUTES,
) -> dict:
    """
    scenario_prices / scenario_freight: one dict per scenario, same shape
    as netback.compute_netback's `prices`/`freight_rates` arguments.
    routes: override the network's route list (e.g. a stress scenario
      with longer transit_days on a rerouted lane).

    Returns {(origin, destination): np.array of netback per scenario}.
    """
    result = {}
    for route in routes:
        key = (route.origin, route.destination)
        vals = [
            compute_netback(route.origin, route.destination, p, f, assumptions, routes).netback_usd_per_mmbtu
            for p, f in zip(scenario_prices, scenario_freight)
        ]
        result[key] = np.array(vals)
    return result


def round_trip_days(route, assumptions: CostAssumptions = CostAssumptions()) -> float:
    if not route.requires_vessel:
        return 0.0
    return 2 * route.transit_days + assumptions.port_loading_discharge_days


def _route_lookup(routes: list[Route] = ROUTES) -> dict:
    return {(r.origin, r.destination): r for r in routes}


def naive_allocation(
    scenario_prices: list[dict],
    scenario_freight: list[dict],
    assumptions: CostAssumptions = CostAssumptions(),
    routes: list[Route] = ROUTES,
    origins: dict = ORIGINS,
) -> dict:
    """
    Each origin ships its *entire* capacity to whichever reachable
    destination has the higher scenario-mean headline price -- not
    netback, and with no regard for whether that destination (or the
    vessel fleet) can actually absorb it. Returns the raw, possibly
    infeasible allocation.
    """
    mean_prices = {k: float(np.mean([p[k] for p in scenario_prices])) for k in scenario_prices[0]}
    allocation = {}
    for origin, cfg in origins.items():
        reachable = [r.destination for r in routes if r.origin == origin]
        best = max(reachable, key=lambda d: destination_price_usd_per_mmbtu(d, mean_prices, assumptions))
        allocation[(origin, best)] = cfg.liquefaction_capacity_cargoes_per_month
    return allocation


def clip_to_capacity(
    allocation: dict,
    assumptions: CostAssumptions = CostAssumptions(),
    routes: list[Route] = ROUTES,
    destinations: dict = DESTINATIONS,
    vessel: dict = VESSEL,
) -> dict:
    """
    Ration an allocation down to respect storage and vessel capacity,
    prorating among origins competing for the same constrained resource.
    Cargoes that don't fit are simply not shipped (lost value) -- this is
    how the naive rule's lack of capacity awareness actually plays out.
    """
    allocation = dict(allocation)
    route_by_key = _route_lookup(routes)

    for dest, cfg in destinations.items():
        keys = [k for k in allocation if k[1] == dest]
        total = sum(allocation[k] for k in keys)
        if total > cfg.storage_capacity_cargoes and total > 0:
            scale = cfg.storage_capacity_cargoes / total
            for k in keys:
                allocation[k] *= scale

    vessel_keys = [k for k in allocation if route_by_key[k].requires_vessel]
    total_vessel_days = sum(allocation[k] * round_trip_days(route_by_key[k], assumptions) for k in vessel_keys)
    fleet_budget = vessel["fleet_size_vessels"] * DAYS_IN_PERIOD
    if total_vessel_days > fleet_budget and total_vessel_days > 0:
        scale = fleet_budget / total_vessel_days
        for k in vessel_keys:
            allocation[k] *= scale

    return allocation


def _add_capacity_constraints(
    prob,
    x,
    assumptions: CostAssumptions = CostAssumptions(),
    routes: list[Route] = ROUTES,
    origins: dict = ORIGINS,
    destinations: dict = DESTINATIONS,
    vessel: dict = VESSEL,
):
    route_by_key = _route_lookup(routes)

    for origin, cfg in origins.items():
        keys = [k for k in x if k[0] == origin]
        if keys:
            prob += pulp.lpSum(x[k] for k in keys) <= cfg.liquefaction_capacity_cargoes_per_month
            if cfg.min_supply_cargoes_per_month > 0:
                # Approximate take-or-pay floor: this origin must ship at
                # least this much *somewhere* it can reach, even to a
                # currently-low-netback destination -- unlike the capacity
                # ceiling above, this can force the LP to accept a worse
                # outcome than "ship nothing," which is the point (real
                # contracts aren't optional every month).
                prob += pulp.lpSum(x[k] for k in keys) >= cfg.min_supply_cargoes_per_month

    for dest, cfg in destinations.items():
        keys = [k for k in x if k[1] == dest]
        if keys:
            prob += pulp.lpSum(x[k] for k in keys) <= cfg.storage_capacity_cargoes

    vessel_keys = [k for k in x if route_by_key[k].requires_vessel]
    if vessel_keys:
        prob += (
            pulp.lpSum(x[k] * round_trip_days(route_by_key[k], assumptions) for k in vessel_keys)
            <= vessel["fleet_size_vessels"] * DAYS_IN_PERIOD
        )


def solve_ev_lp(
    netbacks: dict,
    assumptions: CostAssumptions = CostAssumptions(),
    routes: list[Route] = ROUTES,
    origins: dict = ORIGINS,
    destinations: dict = DESTINATIONS,
    vessel: dict = VESSEL,
) -> tuple[dict, float, str]:
    """
    Maximize expected netback subject to liquefaction/storage/vessel
    capacity. Returns (allocation, objective, status) -- status is
    PuLP's solve status string ("Optimal", "Infeasible", ...). A shocked
    combination of overrides can make the capacity constraints mutually
    infeasible (e.g. a take-or-pay floor above a shocked-down liquefaction
    cap); CBC still returns *some* numbers from its last iteration in
    that case, but they satisfy nothing -- always check status before
    trusting the allocation.
    """
    prob = pulp.LpProblem("expected_value", pulp.LpMaximize)
    x = {k: pulp.LpVariable(f"x_{k[0]}_{k[1]}", lowBound=0) for k in netbacks}

    mean_netback = {k: float(np.mean(v)) for k, v in netbacks.items()}
    prob += pulp.lpSum(x[k] * mean_netback[k] for k in x)
    _add_capacity_constraints(prob, x, assumptions, routes, origins, destinations, vessel)

    prob.solve(pulp.PULP_CBC_CMD(msg=0))
    return {k: v.value() for k, v in x.items()}, pulp.value(prob.objective), pulp.LpStatus[prob.status]


def solve_cvar_lp(
    netbacks: dict,
    risk_lambda: float,
    alpha: float = 0.95,
    assumptions: CostAssumptions = CostAssumptions(),
    routes: list[Route] = ROUTES,
    origins: dict = ORIGINS,
    destinations: dict = DESTINATIONS,
    vessel: dict = VESSEL,
) -> tuple[dict, float, str]:
    """
    Maximize E[netback] - risk_lambda * CVaR_alpha(portfolio loss), same
    capacity constraints as solve_ev_lp(). CVaR via the standard
    Rockafellar-Uryasev LP formulation (loss = negative portfolio
    netback); risk_lambda is the risk-aversion knob -- 0 recovers the
    EV LP exactly, higher values trade expected value for a smaller
    downside tail. Returns (allocation, objective, status) -- see
    solve_ev_lp()'s docstring on why status must be checked.
    """
    n_scenarios = len(next(iter(netbacks.values())))
    prob = pulp.LpProblem("risk_aware", pulp.LpMaximize)
    x = {k: pulp.LpVariable(f"x_{k[0]}_{k[1]}", lowBound=0) for k in netbacks}
    zeta = pulp.LpVariable("zeta", lowBound=None)
    u = [pulp.LpVariable(f"u_{s}", lowBound=0) for s in range(n_scenarios)]

    mean_netback = {k: float(np.mean(v)) for k, v in netbacks.items()}
    cvar = zeta + (1.0 / ((1 - alpha) * n_scenarios)) * pulp.lpSum(u)
    prob += pulp.lpSum(x[k] * mean_netback[k] for k in x) - risk_lambda * cvar

    for s in range(n_scenarios):
        portfolio_netback_s = pulp.lpSum(x[k] * float(netbacks[k][s]) for k in x)
        prob += u[s] >= -portfolio_netback_s - zeta

    _add_capacity_constraints(prob, x, assumptions, routes, origins, destinations, vessel)

    prob.solve(pulp.PULP_CBC_CMD(msg=0))
    return {k: v.value() for k, v in x.items()}, pulp.value(prob.objective), pulp.LpStatus[prob.status]


def evaluate_portfolio(allocation: dict, netbacks: dict) -> np.ndarray:
    """Realized portfolio netback (USD/MMBtu-cargo units) per scenario, given a fixed allocation."""
    n_scenarios = len(next(iter(netbacks.values())))
    total = np.zeros(n_scenarios)
    for k, qty in allocation.items():
        if qty and k in netbacks:
            total += qty * netbacks[k]
    return total


def portfolio_stats(portfolio_values: np.ndarray, cargo_size_mmbtu: float = None, alpha: float = 0.95) -> dict:
    """Summary stats in total USD (portfolio_values * cargo_size) if cargo_size_mmbtu given, else raw units."""
    scale = cargo_size_mmbtu or 1.0
    v = portfolio_values * scale
    var_threshold = np.quantile(v, 1 - alpha)
    cvar = v[v <= var_threshold].mean()
    return {
        "mean": float(v.mean()),
        "std": float(v.std()),
        "min": float(v.min()),
        "max": float(v.max()),
        f"VaR{int(alpha*100)}": float(var_threshold),
        f"CVaR{int(alpha*100)}": float(cvar),
        "sharpe_like": float(v.mean() / v.std()) if v.std() > 0 else float("nan"),
        "worst_case_shortfall_pct": float((v.mean() - v.min()) / v.mean() * 100) if v.mean() else float("nan"),
    }


def capacity_utilization(
    allocation: dict,
    assumptions: CostAssumptions = CostAssumptions(),
    routes: list[Route] = ROUTES,
    origins: dict = ORIGINS,
    destinations: dict = DESTINATIONS,
    vessel: dict = VESSEL,
) -> dict:
    """
    Utilization % of liquefaction (by origin), storage (by destination),
    and the vessel fleet, given a fixed allocation. A single-period
    snapshot -- there's no time series in this model to compute a true
    max drawdown from, so this (plus VaR/CVaR/sharpe_like in
    portfolio_stats) is the risk-metric set Phase 5's stress tests
    report instead.
    """
    route_by_key = _route_lookup(routes)

    liquefaction = {
        origin: sum(allocation.get(k, 0) for k in allocation if k[0] == origin) / cfg.liquefaction_capacity_cargoes_per_month
        for origin, cfg in origins.items()
    }
    storage = {
        dest: sum(allocation.get(k, 0) for k in allocation if k[1] == dest) / cfg.storage_capacity_cargoes
        for dest, cfg in destinations.items()
    }
    vessel_days_used = sum(
        allocation.get(k, 0) * round_trip_days(route_by_key[k], assumptions)
        for k in allocation
        if route_by_key[k].requires_vessel
    )
    vessel_fleet = vessel_days_used / (vessel["fleet_size_vessels"] * DAYS_IN_PERIOD)

    return {"liquefaction_by_origin": liquefaction, "storage_by_destination": storage, "vessel_fleet": vessel_fleet}
