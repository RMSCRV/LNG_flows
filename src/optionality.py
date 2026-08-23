"""
Phase 4: optionality experiment.

For a small set of illustrative cargoes, compare two strategies:

- commit-now: pick the destination today (using only currently-known
  prices), lock it in, and realize whatever netback results at delivery.
- wait-and-redirect: hold the destination decision open for one week,
  then choose based on that week's realized prices, and still realize
  the payoff at the same final delivery date.

    V_option = E[Payoff_flexible] - E[Payoff_committed]

This is a small, single-cargo marginal analysis -- deliberately not run
through the Phase 3 LP, since it's asking "what is flexibility worth on
one cargo" rather than "how should a whole portfolio be allocated".
Liquefaction/storage/vessel capacity are not enforced here for that
reason; see notebooks/04_optimization_engine.ipynb for the
capacity-aware portfolio problem.
"""

import numpy as np

from netback import CostAssumptions, compute_netback, compute_netback_all_destinations
from network_config import ORIGINS
from simulator import HubParams, rescale_dt, simulate_paths

WEEKS_TO_DELIVERY = 4  # ~1 month, matching Phase 3's monthly cargo cadence
DECISION_WEEK = 1  # "wait one decision point" per the aims doc


def weekly_params(monthly_params: list[HubParams]) -> list[HubParams]:
    """Re-express monthly-calibrated params at weekly resolution (dt=1/52).

    theta/sigma carry over unchanged (continuous-time rates); jump_prob
    is rescaled to preserve the implied annual jump rate. Correlation
    structure is assumed unchanged across frequencies -- a simplification,
    not something separately estimated at weekly resolution (no weekly
    data exists for any hub in this project).
    """
    return [rescale_dt(p, 1 / 52) for p in monthly_params]


def simulate_decision_scenarios(
    monthly_params: list[HubParams],
    corr_matrix,
    start_prices: dict,
    n_scenarios: int,
    seed: int = None,
) -> dict:
    """Simulate weekly paths out to WEEKS_TO_DELIVERY and return the two
    checkpoints needed: prices/freight at the decision week and at delivery.

    Returns {"decision": {hub: array[n_scenarios]}, "delivery": {hub: array[n_scenarios]}}.
    """
    params = weekly_params(monthly_params)
    paths = simulate_paths(
        params, corr_matrix, n_paths=n_scenarios, n_steps=WEEKS_TO_DELIVERY, start_prices=start_prices, seed=seed
    )
    return {
        "decision": {hub: arr[:, DECISION_WEEK] for hub, arr in paths.items()},
        "delivery": {hub: arr[:, WEEKS_TO_DELIVERY] for hub, arr in paths.items()},
    }


def _split(checkpoint: dict, i: int) -> tuple[dict, dict]:
    """One scenario's prices/freight dicts, split into netback.py's expected shapes."""
    prices = {"HENRY_HUB": checkpoint["HENRY_HUB"][i], "TTF": checkpoint["TTF"][i], "JKM": checkpoint["JKM"][i]}
    freight = {"FREIGHT_ATLANTIC": checkpoint["FREIGHT_ATLANTIC"][i], "FREIGHT_PACIFIC": checkpoint["FREIGHT_PACIFIC"][i]}
    return prices, freight


def evaluate_optionality(
    origin: str,
    scenarios: dict,
    start_prices: dict,
    start_freight: dict,
    assumptions: CostAssumptions = CostAssumptions(),
) -> dict:
    """
    V_option for one origin's cargo, evaluated across all scenarios in
    `scenarios` (output of simulate_decision_scenarios).
    """
    n = len(scenarios["decision"]["HENRY_HUB"])

    committed_dest = compute_netback_all_destinations(origin, start_prices, start_freight, assumptions)[0].destination

    payoff_committed = np.zeros(n)
    payoff_flexible = np.zeros(n)
    flexible_dest = []

    for i in range(n):
        decision_prices, decision_freight = _split(scenarios["decision"], i)
        delivery_prices, delivery_freight = _split(scenarios["delivery"], i)

        best_at_decision = compute_netback_all_destinations(origin, decision_prices, decision_freight, assumptions)[0].destination
        flexible_dest.append(best_at_decision)

        payoff_committed[i] = compute_netback(origin, committed_dest, delivery_prices, delivery_freight, assumptions).netback_usd_per_mmbtu
        payoff_flexible[i] = compute_netback(origin, best_at_decision, delivery_prices, delivery_freight, assumptions).netback_usd_per_mmbtu

    redirect_rate = float(np.mean([d != committed_dest for d in flexible_dest]))

    return {
        "origin": origin,
        "committed_destination": committed_dest,
        "mean_payoff_committed": float(payoff_committed.mean()),
        "mean_payoff_flexible": float(payoff_flexible.mean()),
        "v_option_usd_per_mmbtu": float(payoff_flexible.mean() - payoff_committed.mean()),
        "redirect_rate": redirect_rate,
        "payoff_committed": payoff_committed,
        "payoff_flexible": payoff_flexible,
    }
