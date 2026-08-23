"""
Phase 2: netback calculator.

    Netback = P_dest - C_shipping - C_liquefaction - C_variable - C_hedging

Given an origin, a destination, and a price scenario (spot values for
HENRY_HUB/TTF/JKM plus freight day-rates for the Atlantic/Pacific
basins), returns the netback in USD/MMBtu -- the number that actually
matters for a routing decision, as opposed to the destination's
headline price alone.

Cost assumptions (liquefaction, variable, hedging, FX, port/loading
buffer) are illustrative placeholders sized to plausible industry
ranges, not sourced figures -- see the docstring on CostAssumptions.
"""

from dataclasses import dataclass

from network_config import DESTINATIONS, ORIGINS, ROUTES, VESSEL, Route


@dataclass(frozen=True)
class CostAssumptions:
    """
    All illustrative, not sourced:
    - liquefaction: typical published US Gulf Coast tolling fees run
      roughly $2-3.5/MMBtu; 2.50 picked as a round mid-range figure and
      applied uniformly across origins for simplicity (in reality
      Qatar/Australia's integrated projects have a different cost
      structure than a US tolling model).
    - variable: port fees, boil-off allowance, insurance -- a smaller
      line item than liquefaction or shipping.
    - hedging: cost of hedging price/basis risk on the voyage.
    - fx_usd_per_eur: spot-checked at ~1.17 (Aug 2026); re-verify before
      relying on this for anything beyond an illustrative comparison.
    - mmbtu_per_mwh: standard HHV-basis physical conversion (1 MWh =
      3.6 GJ, 1 MMBtu = 1.055056 GJ), not an assumption.
    - port_loading_discharge_days: added to 2x one-way transit_days to
      get total vessel-employment days per round trip.
    """

    liquefaction_usd_per_mmbtu: float = 2.50
    variable_usd_per_mmbtu: float = 0.15
    hedging_usd_per_mmbtu: float = 0.05
    fx_usd_per_eur: float = 1.17
    mmbtu_per_mwh: float = 3.412
    port_loading_discharge_days: float = 3.0


@dataclass(frozen=True)
class NetbackResult:
    origin: str
    destination: str
    p_dest_usd_per_mmbtu: float
    c_shipping_usd_per_mmbtu: float
    c_liquefaction_usd_per_mmbtu: float
    c_variable_usd_per_mmbtu: float
    c_hedging_usd_per_mmbtu: float
    netback_usd_per_mmbtu: float
    netback_usd_per_cargo: float


def find_route(origin: str, destination: str, routes: list[Route] = ROUTES) -> Route:
    for r in routes:
        if r.origin == origin and r.destination == destination:
            return r
    raise ValueError(f"no route from {origin} to {destination}")


def basin_for_destination(destination: str) -> str | None:
    """Which freight basin prices a destination's inbound voyages.

    Destination determines the basin (not origin): any Europe-bound
    cargo is priced off the Atlantic day-rate, any Asia-bound cargo off
    the Pacific day-rate, regardless of which origin it sails from --
    this is the fallback documented in docs/DATA_ACCESS.md for the
    Qatar lanes (no dedicated Qatar freight index exists), generalized
    to apply uniformly rather than as a special case.
    """
    if destination == "EUROPE":
        return "FREIGHT_ATLANTIC"
    if destination == "ASIA":
        return "FREIGHT_PACIFIC"
    return None  # US_DOMESTIC: no vessel, no basin


def destination_price_usd_per_mmbtu(destination: str, prices: dict, assumptions: CostAssumptions) -> float:
    hub = DESTINATIONS[destination].price_hub
    raw = prices[hub]
    if hub == "TTF":  # EUR/MWh -> USD/MMBtu
        return raw / assumptions.mmbtu_per_mwh * assumptions.fx_usd_per_eur
    return raw  # JKM, HENRY_HUB already USD/MMBtu


def freight_cost_usd_per_mmbtu(route: Route, freight_rates: dict, assumptions: CostAssumptions) -> float:
    if not route.requires_vessel:
        return 0.0
    basin = basin_for_destination(route.destination)
    day_rate = freight_rates[basin]
    round_trip_days = 2 * route.transit_days + assumptions.port_loading_discharge_days
    return day_rate * round_trip_days / VESSEL["cargo_size_mmbtu"]


def compute_netback(
    origin: str,
    destination: str,
    prices: dict,
    freight_rates: dict,
    assumptions: CostAssumptions = CostAssumptions(),
    routes: list[Route] = ROUTES,
) -> NetbackResult:
    """
    prices: {"HENRY_HUB": usd_per_mmbtu, "TTF": eur_per_mwh, "JKM": usd_per_mmbtu}
    freight_rates: {"FREIGHT_ATLANTIC": usd_per_day, "FREIGHT_PACIFIC": usd_per_day}
    routes: override the network's route list (e.g. a stress scenario
      with longer transit_days on a rerouted lane) -- defaults to the
      real network.
    """
    route = find_route(origin, destination, routes)
    p_dest = destination_price_usd_per_mmbtu(destination, prices, assumptions)

    if route.requires_vessel:
        c_shipping = freight_cost_usd_per_mmbtu(route, freight_rates, assumptions)
        c_liq = assumptions.liquefaction_usd_per_mmbtu
        c_var = assumptions.variable_usd_per_mmbtu
        c_hedge = assumptions.hedging_usd_per_mmbtu
    else:
        # US Domestic: selling feedgas into Henry Hub directly, no
        # liquefaction/shipping/export-hedging costs apply.
        c_shipping = c_liq = c_var = c_hedge = 0.0

    netback = p_dest - c_shipping - c_liq - c_var - c_hedge
    return NetbackResult(
        origin=origin,
        destination=destination,
        p_dest_usd_per_mmbtu=p_dest,
        c_shipping_usd_per_mmbtu=c_shipping,
        c_liquefaction_usd_per_mmbtu=c_liq,
        c_variable_usd_per_mmbtu=c_var,
        c_hedging_usd_per_mmbtu=c_hedge,
        netback_usd_per_mmbtu=netback,
        netback_usd_per_cargo=netback * VESSEL["cargo_size_mmbtu"],
    )


def compute_netback_all_destinations(
    origin: str,
    prices: dict,
    freight_rates: dict,
    assumptions: CostAssumptions = CostAssumptions(),
    routes: list[Route] = ROUTES,
) -> list[NetbackResult]:
    """Netback from `origin` to every destination it has a route to, sorted best-first."""
    destinations = [r.destination for r in routes if r.origin == origin]
    results = [compute_netback(origin, d, prices, freight_rates, assumptions, routes) for d in destinations]
    return sorted(results, key=lambda r: r.netback_usd_per_mmbtu, reverse=True)
