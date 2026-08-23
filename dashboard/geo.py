"""
Phase 6: map coordinates and shock explanations for the dashboard.

Node coordinates are approximate real-world locations for the network's
origins/destinations (illustrative placement, not exact facility
coordinates) -- purely for the stylized map layout, no bearing on the
underlying economics in src/.
"""

# Hand-simplified continent silhouettes, (lon, lat) points, for the
# self-contained map background -- see map_view.py's docstring for why
# these are drawn by hand rather than fetched from a topojson service.
# Deliberately low-vertex and approximate; "stylized", not surveyed.
CONTINENTS = [
    [  # North America
        (-168, 66), (-165, 60), (-155, 58), (-135, 58), (-130, 55), (-125, 48),
        (-124, 40), (-117, 32), (-105, 20), (-97, 16), (-90, 14), (-85, 10),
        (-81, 9), (-80, 25), (-76, 35), (-70, 41), (-65, 45), (-60, 47),
        (-55, 51), (-60, 55), (-65, 60), (-75, 62), (-85, 68), (-95, 70),
        (-110, 72), (-130, 70), (-150, 71), (-165, 68),
    ],
    [  # South America
        (-77, 8), (-70, 11), (-60, 8), (-51, 4), (-45, -3), (-35, -8),
        (-38, -18), (-42, -23), (-48, -26), (-53, -34), (-58, -38),
        (-62, -42), (-68, -45), (-70, -52), (-73, -53), (-75, -50),
        (-71, -40), (-71, -30), (-70, -18), (-71, -10), (-77, 0),
    ],
    [  # Europe
        (-9, 43), (-9, 51), (-5, 48), (-1, 49), (2, 51), (5, 53), (8, 55),
        (10, 57), (12, 55), (18, 55), (20, 54), (23, 55), (28, 60), (30, 60),
        (35, 55), (40, 50), (38, 46), (35, 45), (30, 44), (28, 41), (23, 40),
        (20, 40), (17, 40), (14, 38), (12, 42), (9, 44), (6, 43), (3, 42),
        (-2, 37), (-6, 37), (-9, 38),
    ],
    [  # Africa
        (-17, 21), (-17, 15), (-16, 12), (-11, 7), (-8, 5), (0, 5), (9, 4),
        (9, -2), (13, -6), (12, -18), (14, -22), (18, -34), (26, -34),
        (32, -29), (35, -22), (40, -15), (42, -5), (48, 1), (51, 10),
        (44, 12), (43, 18), (37, 22), (35, 27), (32, 31), (25, 32),
        (25, 31), (20, 31), (11, 33), (10, 36), (2, 37), (-6, 35),
        (-10, 30), (-13, 27),
    ],
    [  # Asia
        (26, 42), (30, 46), (40, 47), (48, 42), (50, 40), (48, 38), (54, 37),
        (60, 42), (55, 45), (60, 50), (65, 55), (70, 55), (75, 52), (80, 51),
        (87, 50), (95, 50), (105, 52), (115, 50), (120, 45), (125, 43),
        (130, 46), (135, 45), (140, 45), (142, 43), (140, 36), (135, 34),
        (130, 34), (129, 37), (126, 38), (124, 40), (122, 38), (120, 32),
        (122, 30), (120, 25), (110, 20), (108, 16), (102, 12), (100, 10),
        (98, 8), (95, 5), (92, 15), (88, 22), (80, 8), (77, 8), (72, 21),
        (68, 24), (61, 25), (57, 26), (56, 27), (52, 30), (48, 30), (45, 30),
        (40, 33), (36, 37), (30, 37),
    ],
    [  # Australia
        (113, -22), (114, -26), (114, -32), (115, -34), (118, -35), (122, -34),
        (126, -32), (129, -32), (131, -32), (134, -33), (137, -35), (140, -38),
        (144, -38), (146, -39), (150, -37), (153, -29), (153, -25), (150, -22),
        (145, -17), (143, -14), (141, -12), (137, -12), (133, -12), (130, -12),
        (127, -14), (123, -17), (121, -18), (117, -20),
    ],
]

NODE_COORDS = {
    "US_GC": {"lat": 29.7, "lon": -93.9, "label": "US Gulf Coast", "kind": "origin"},
    "QATAR": {"lat": 25.9, "lon": 51.5, "label": "Qatar", "kind": "origin"},
    "AUSTRALIA": {"lat": -20.7, "lon": 116.8, "label": "Australia (NW Shelf)", "kind": "origin"},
    "EUROPE": {"lat": 51.9, "lon": 4.5, "label": "Europe (TTF, Rotterdam)", "kind": "destination"},
    "ASIA": {"lat": 35.6, "lon": 139.8, "label": "Asia (JKM, Tokyo Bay)", "kind": "destination"},
    "US_DOMESTIC": {"lat": 30.2, "lon": -91.2, "label": "US Domestic (Henry Hub)", "kind": "destination"},
}

# Hover/help text shown on shock controls -- each explains a plausible
# real-world trigger and why the mechanic matters for the network, per
# the aims doc's request that shocks be traceable to a real situation.
SHOCK_INFO = {
    "ttf": (
        "European gas prices spike when winter demand is high and storage "
        "is running below the 5-year seasonal average -- the 2021-22 "
        "energy crisis (Russian pipeline cuts) is the extreme case, but "
        "milder versions recur most cold winters. A higher TTF pulls more "
        "cargoes toward Europe at the expense of Asia and US domestic."
    ),
    "jkm": (
        "Asian spot LNG prices spike on hot summers (air-conditioning "
        "demand), cold winters, or a nuclear/coal outage forcing more gas "
        "burn -- Japan and South Korea are the marginal buyers most years. "
        "A higher JKM pulls cargoes toward Asia and away from Europe."
    ),
    "freight_atlantic": (
        "Atlantic day-rates rise when vessel supply tightens -- winter "
        "ice-class demand, a wave of newbuild deliveries being absorbed "
        "slower than expected, or a chokepoint disruption forcing longer "
        "voyages (see the route disruption controls below)."
    ),
    "freight_pacific": (
        "Pacific day-rates move on the same fleet-tightness logic as the "
        "Atlantic, plus its own seasonal Asian winter/summer demand peaks "
        "for spot cargoes that compete with the LNG fleet for tonnage."
    ),
    "europe_storage": (
        "European storage capacity is effectively reduced when facilities "
        "are already fuller than usual heading into the shock (less spare "
        "room to absorb more cargoes), or after a real outage/maintenance "
        "event at a specific terminal. Binds harder in winter."
    ),
    "asia_storage": (
        "Asian (mainly Japan/Korea/China) terminal storage is more rigid "
        "than Europe's -- less flexible underground storage, more "
        "just-in-time send-out -- so a capacity cut here reflects a "
        "terminal outage or an unusually high existing inventory."
    ),
    "us_domestic_storage": (
        "The US domestic outlet's capacity stands in for how much Henry "
        "Hub demand can realistically absorb -- a cut here approximates a "
        "mild winter or industrial demand slump reducing that outlet."
    ),
    "liquefaction": (
        "An unplanned outage (train trip, feedgas curtailment, storm "
        "damage) or scheduled maintenance takes part of an origin's "
        "liquefaction capacity offline for the month -- Freeport LNG's "
        "2022 fire is the textbook example of this at US Gulf Coast scale."
    ),
    "vessel_fleet": (
        "The available fleet shrinks in drydock/maintenance season, when "
        "vessels are chartered out to other trades, or during a broader "
        "shipping-market squeeze. Since the fleet is usually the tightest "
        "constraint in this network, small cuts here can move a lot."
    ),
    "suez": (
        "Red Sea/Suez transits get rerouted around the Cape of Good Hope "
        "during a chokepoint disruption (e.g. the 2023-24 Houthi attacks) "
        "-- this lengthens Qatar->Europe voyages substantially, which "
        "matters because that's normally Qatar's short route to Europe."
    ),
    "panama": (
        "Panama Canal transits get delayed or restricted during a drought "
        "(the 2023 low-water-level restrictions are the recent real "
        "example) -- this lengthens US Gulf Coast->Asia voyages, which "
        "would otherwise use the Canal as the short path west."
    ),
    "min_supply": (
        "Real LNG offtake is mostly locked into long-term take-or-pay "
        "contracts: the seller must deliver (or the buyer must pay for) a "
        "minimum volume most months regardless of spot economics. Raising "
        "this floor makes an origin less free to sit out a bad month; "
        "lowering it approximates a more spot-exposed portfolio."
    ),
    "risk_lambda": (
        "How much the risk-aware strategy penalizes downside tail risk "
        "(CVaR at the 95th percentile) relative to expected value. 0 "
        "recovers the plain expected-value optimum; higher values trade "
        "away average profit for a smaller worst-case shortfall."
    ),
    "duration": (
        "How many months the shock is assumed to persist. The underlying "
        "optimization is single-period (one representative month), so "
        "this scales the shown cumulative impact by duration as a simple "
        "approximation -- it does NOT re-simulate a multi-month path "
        "where, e.g., storage could refill or contracts could be "
        "renegotiated between months. Treat the cumulative figure as "
        "directional, not a forecast."
    ),
}
