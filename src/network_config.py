"""
Stylized LNG network for the MVP.

3 liquefaction origins, 2 export destinations, plus a domestic
consumption outlet for the US origin only:

    US Gulf Coast  --> Europe (TTF), Asia (JKM), US Domestic (Henry Hub)
    Qatar          --> Europe (TTF), Asia (JKM)
    Australia      --> Europe (TTF), Asia (JKM)

US Domestic is not a shipping lane: it represents the US origin choosing
not to liquefy/export a given volume and instead selling it into the
domestic Henry Hub market. Qatar and Australia have no domestic outlet
in this model (no analogous liquid public benchmark for stranded gas at
those origins), so they can only route to Europe or Asia.

Capacity and distance figures below are illustrative placeholders sized
to roughly the right order of magnitude for real facilities/routes, not
sourced values. Phase 2 (netback calculator) is where these get revisited
alongside real cost data; don't treat them as calibrated.
"""

import dataclasses
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Origin:
    name: str
    price_hub: str  # price series driving feedstock/opportunity cost
    liquefaction_capacity_cargoes_per_month: float
    has_domestic_outlet: bool = False
    # Approximate take-or-pay floor: real LNG offtake is mostly locked into
    # long-term contracts that must ship (to *some* destination) regardless
    # of price, not spot-shopped freely every month. 0.0 means fully
    # discretionary. Illustrative, not sourced -- see module docstring.
    min_supply_cargoes_per_month: float = 0.0


@dataclass(frozen=True)
class Destination:
    name: str
    price_hub: str  # price series this destination sells into
    storage_capacity_cargoes: float
    requires_vessel: bool = True  # False only for the US domestic outlet


@dataclass(frozen=True)
class Route:
    origin: str
    destination: str
    transit_days: float
    requires_vessel: bool


ORIGINS = {
    "US_GC": Origin(
        name="US Gulf Coast",
        price_hub="HENRY_HUB",
        liquefaction_capacity_cargoes_per_month=8.0,
        has_domestic_outlet=True,
        # US offtake skews toward destination-flexible FOB contracts with more
        # merchant/spot volume, so a lower take-or-pay floor (~35%).
        min_supply_cargoes_per_month=3.0,
    ),
    "QATAR": Origin(
        name="Qatar",
        price_hub="HENRY_HUB",  # Qatar has no liquid public feedstock price; Henry Hub used only as a placeholder cost driver until Phase 2
        liquefaction_capacity_cargoes_per_month=12.0,
        # Qatar's exports skew toward long-term take-or-pay SPAs (~58% floor).
        min_supply_cargoes_per_month=7.0,
    ),
    "AUSTRALIA": Origin(
        name="Australia",
        price_hub="HENRY_HUB",  # same placeholder caveat as Qatar
        liquefaction_capacity_cargoes_per_month=7.0,
        # Similarly majority long-term-contracted (~57% floor).
        min_supply_cargoes_per_month=4.0,
    ),
}

DESTINATIONS = {
    "EUROPE": Destination(
        name="Europe",
        price_hub="TTF",
        storage_capacity_cargoes=15.0,
    ),
    "ASIA": Destination(
        name="Asia",
        price_hub="JKM",
        storage_capacity_cargoes=15.0,
    ),
    "US_DOMESTIC": Destination(
        name="US Domestic",
        price_hub="HENRY_HUB",
        storage_capacity_cargoes=20.0,
        requires_vessel=False,
    ),
}

# Approximate one-way transit days per route (generic vessel, ~17-19 knots).
# US_GC -> Asia assumes Panama Canal transit; Australia -> Europe assumes
# Cape of Good Hope / Suez and is deliberately long+expensive so the LP
# should almost never pick it, which is itself worth noting in the writeup.
ROUTES = [
    Route("US_GC", "EUROPE", transit_days=9, requires_vessel=True),
    Route("US_GC", "ASIA", transit_days=22, requires_vessel=True),
    Route("US_GC", "US_DOMESTIC", transit_days=0, requires_vessel=False),
    Route("QATAR", "EUROPE", transit_days=9, requires_vessel=True),
    Route("QATAR", "ASIA", transit_days=9, requires_vessel=True),
    Route("AUSTRALIA", "ASIA", transit_days=7, requires_vessel=True),
    Route("AUSTRALIA", "EUROPE", transit_days=28, requires_vessel=True),
]

VESSEL = {
    "name": "Generic 174k m3 LNG carrier",
    "cargo_size_mmbtu": 3_000_000.0,  # ~one cargo, illustrative
    "fleet_size_vessels": 10.0,
}


def routes_from(origin: str) -> list[Route]:
    return [r for r in ROUTES if r.origin == origin]


def routes_to(destination: str) -> list[Route]:
    return [r for r in ROUTES if r.destination == destination]


def with_route_overrides(overrides: dict[tuple[str, str], float]) -> list[Route]:
    """
    A copy of ROUTES with transit_days replaced for specific
    (origin, destination) lanes -- e.g. a stress scenario where a
    chokepoint disruption forces a longer reroute. Does not mutate the
    global ROUTES list.
    """
    result = []
    for r in ROUTES:
        key = (r.origin, r.destination)
        if key in overrides:
            result.append(Route(r.origin, r.destination, overrides[key], r.requires_vessel))
        else:
            result.append(r)
    return result


def with_origin_overrides(
    liquefaction: dict[str, float] | None = None,
    min_supply: dict[str, float] | None = None,
) -> dict[str, Origin]:
    """
    A copy of ORIGINS with liquefaction capacity and/or the take-or-pay
    floor replaced for specific origin keys -- e.g. a dashboard shock
    representing an unplanned outage (lower capacity) or a renegotiated
    contract (different min_supply). Does not mutate the global ORIGINS
    dict. Either dict may be partial or omitted.
    """
    liquefaction = liquefaction or {}
    min_supply = min_supply or {}
    result = {}
    for key, o in ORIGINS.items():
        changes = {}
        if key in liquefaction:
            changes["liquefaction_capacity_cargoes_per_month"] = liquefaction[key]
        if key in min_supply:
            changes["min_supply_cargoes_per_month"] = min_supply[key]
        result[key] = dataclasses.replace(o, **changes) if changes else o
    return result


def with_destination_overrides(storage: dict[str, float]) -> dict[str, Destination]:
    """
    A copy of DESTINATIONS with storage capacity replaced for specific
    destination keys -- e.g. a dashboard shock representing a European
    storage drawdown (less spare capacity to absorb cargoes) or a
    maintenance outage. Does not mutate the global DESTINATIONS dict.
    """
    result = {}
    for key, d in DESTINATIONS.items():
        if key in storage:
            result[key] = dataclasses.replace(d, storage_capacity_cargoes=storage[key])
        else:
            result[key] = d
    return result


def with_vessel_overrides(fleet_size_vessels: float) -> dict:
    """A copy of VESSEL with fleet size replaced -- e.g. a charter-market shock."""
    return {**VESSEL, "fleet_size_vessels": fleet_size_vessels}


if __name__ == "__main__":
    for o in ORIGINS:
        dests = ", ".join(r.destination for r in routes_from(o))
        print(f"{o} -> {dests}")
