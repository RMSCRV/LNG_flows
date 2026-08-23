# LNG Flows MVP

Stylized LNG trading/optimization project: simulate correlated hub prices,
compute netbacks across a small physical network, and compare a naive
highest-price rule against expected-value and risk-aware LP allocation.
See the full roadmap in the repo root discussion / project notes.

End goal includes an interactive dashboard (Streamlit) where prices,
freight rates, and capacities are adjustable shocks -- so calibration
being directionally right matters more than being a precise historical
fit; several assumptions below are flagged accordingly.

## Status: Phase 6 (dashboard) -- built

- **`dashboard/app.py`** (`streamlit run dashboard/app.py`): the
  interactive "shock it and see" tool that was the whole project's end
  goal. A sidebar shock panel (price, freight, storage/liquefaction
  capacity, vessel fleet, take-or-pay floors, route disruptions, risk
  aversion, and an approximate shock duration) feeds into `src/`'s real
  override mechanisms -- nothing is mocked or re-implemented for the
  dashboard -- and re-solves both the expected-value and risk-aware LPs
  on every "Apply Shock" press.
  - **Map**: a stylized world map (`dashboard/map_view.py`) built as a
    plain Cartesian lon/lat scatter with hand-simplified continent
    silhouettes, deliberately *not* `go.Scattergeo` -- that trace type
    needs Plotly's JS runtime to fetch topojson coastline data from
    `cdn.plot.ly` at render time, which fails in a network-restricted
    environment and is a fragile external dependency for any deployment
    (the same no-API-key ethos as Phase 0). Nodes are sized by
    utilization and colored by role (origin/destination); links are
    colored red-to-green by netback and sized by cargoes shipped; both
    carry native Plotly hover tooltips.
  - **Info-on-hover**: every shock control uses Streamlit's native
    `help=` parameter, so hovering its (?) icon explains a real
    situation that would cause that shock and why it matters (e.g. the
    Europe storage slider explains it approximates a terminal outage or
    an unusually full facility heading into winter) -- `dashboard/geo.py`
    holds all of this text (`SHOCK_INFO`) so it's easy to extend.
  - **Before/after comparison**: `st.metric`'s built-in delta indicators
    show expected value, CVaR95, vessel-fleet utilization, and
    worst-case shortfall shifting from an unshocked baseline (same risk
    lambda, so a lambda change isn't miscounted as a "shock" effect) to
    the shocked scenario.
  - **Infeasibility handling**: `solve_ev_lp()`/`solve_cvar_lp()` now
    return a solver status alongside the allocation (see below) --
    a shock combination that leaves a take-or-pay floor above a
    shocked-down capacity is genuinely infeasible, and the dashboard
    shows a clear explanation instead of silently displaying CBC's
    leftover (meaningless) numbers from an infeasible solve. Verified by
    deliberately cutting Qatar's liquefaction capacity below its floor.
  - Verified interactively (Playwright): the TTF x1.6 shock reproduces
    Phase 5's EU-winter-shock finding exactly (Australia pinned to its
    4.0-cargo floor, portfolio value up to ~$1.16B/month), and the
    risk-aware toggle reproduces Phase 3's Qatar-reallocation finding.
  - Runs on **1000 scenarios** rather than Phase 3/5's 2000, traded for
    interactive responsiveness; the baseline scenario generation is
    cached (`st.cache_data`), so only the (fast) LP re-solve happens on
    each shock.
- **`src/network_config.py`** gained `with_origin_overrides()`,
  `with_destination_overrides()`, and `with_vessel_overrides()` --
  the same override pattern `with_route_overrides()` already used for
  Phase 5's route disruptions, extended to capacity so the dashboard
  can shock liquefaction, storage, take-or-pay floors, and fleet size
  without mutating global state. `src/optimization.py`'s functions all
  gained matching optional `origins`/`destinations`/`vessel` parameters.
- **`solve_ev_lp()`/`solve_cvar_lp()`** now return a 3-tuple
  `(allocation, objective, status)` instead of 2 -- `status` is PuLP's
  solve status string, and must be checked before trusting the
  allocation (an infeasible solve still returns *some* numbers from
  CBC's last iteration, but they satisfy nothing). Notebooks 04 and 06
  were updated to assert `status == "Optimal"` and re-verified to still
  produce identical numbers to before this change.

## Status: Phase 5 (stress tests) -- built

- **`notebooks/06_stress_tests.ipynb`**: re-runs Phase 3's exact EV LP and
  risk-aware LP (same 2000-scenario baseline, seed=7, for direct
  comparability) under three shocks -- a demand shock, a competing-basin
  demand shock, and a supply-side disruption -- via
  `network_config.with_route_overrides()` for the routing shock and a
  `shock()` helper that multiplies simulated prices/freight for the price
  shocks:
  - **EU winter demand shock** (TTF x1.6): the EV LP's response is more
    dramatic than a simple reallocation -- Qatar's exports concentrate
    almost entirely in Europe, consuming nearly the *entire* vessel fleet,
    and **Australia gets pushed down to exactly its 4.0-cargo take-or-pay
    floor** (57% liquefaction utilization, down from 100% in the
    baseline) rather than being optimized out to zero. Without that floor
    the LP's pure profit-maximizing corner solution actually does push
    Australia to 0% -- verified by hand via vessel-day arithmetic, not a
    bug -- so the floor is precisely what turns a clean (if slightly
    unrealistic) corner solution into a more realistic constrained one.
    Portfolio value rises to **$1.16B/month** (from $845M baseline) since
    the shock is a pure demand increase.
  - The risk-aware LP (`lambda=2.0`) makes the **identical** allocation
    choice on every route, not just Australia's floored total -- no
    diversification of the *discretionary* fleet away from Europe. This is
    a genuine, if slightly counterintuitive, finding: CVaR penalizes
    portfolio-level tail risk, not geographic concentration specifically,
    and here concentrating in Europe is both the highest-expected-value
    *and* lowest-tail-risk option, so there's no risk-return trade-off left
    for `lambda` to exploit. Portfolio-level risk-awareness is not the same
    thing as diversification-by-construction -- worth stating explicitly
    since it's easy to assume otherwise; if anything, the take-or-pay floor
    above is doing more real diversification work here than `lambda` is.
  - **Asia demand surge** (JKM x1.5) reinforces the already-Asia-leaning
    baseline allocation rather than flipping anything -- Asia already wins
    for every origin in the current snapshot, so the surge widens the
    margin (value up to $1.28B/month) without changing the ranking.
  - **Shipping disruption** (freight rates x2, plus Qatar-Europe and
    US_GC-Asia rerouted to longer transit times) is the one shock that
    changes *feasibility*, not just relative value: the vessel fleet
    constraint -- already binding in the Phase 3 baseline -- gets tighter
    still, and portfolio value **falls even after re-optimizing** ($845M
    -> $829M). Unlike the two demand shocks, this is the only one that
    makes the network strictly worse off rather than just reshuffling who
    benefits.
  - Same risk-metric adaptations as Phase 3 (VaR95/CVaR95/sharpe_like/
    worst-case-shortfall in place of a true Sharpe ratio or max drawdown,
    since this is a single-period model with no time series) plus
    liquefaction/storage/vessel-fleet utilization by scenario.
  - Results saved to `data/processed/stress_tests/`.

## Status: Phase 4 (optionality) -- built

- **`src/optionality.py`**: compares commit-now vs. wait-and-redirect for
  one cargo per origin, via `notebooks/05_optionality.ipynb`. Both
  strategies decide by netback, not headline price (unlike Phase 3's
  naive baseline) -- this compares two *rational* strategies, not
  rational vs. naive. Simulates weekly-resolution paths (`rescale_dt()`
  re-expresses the monthly calibration at dt=1/52) out to a 1-week
  decision point and 1-month delivery.
  - `V_option` is positive for every origin (flexibility always has some
    value) and scales with how many destinations an origin can reach:
    **US_GC ($0.31/MMBtu, 3 destinations incl. domestic) > Qatar
    ($0.20/MMBtu, 2) > Australia ($0.08/MMBtu, 2)**. Australia's low
    value makes sense -- its Europe route is so much more expensive
    (long Cape voyage) that price moves rarely flip the decision away
    from Asia, so there's less genuine ambiguity to exploit.
  - Redirect rate (how often the flexible strategy actually switches
    destination) tracks the same pattern: 45.5% (US_GC) down to 22.7%
    (Australia).
  - Explicitly related back to Phase 1's coverage checks per the aims
    doc's request: TTF/JKM calibration (79-89% coverage) is solid enough
    to trust this number, but a freight-driven optionality question
    would be shakier, since freight's coverage check came in at only
    ~65%.
  - Results saved to `data/processed/optionality/v_option.json`.

## Status: Phase 3 (optimization engine) -- built, now with take-or-pay floors

- Each origin in `network_config.py` now carries an approximate
  **take-or-pay minimum** (`min_supply_cargoes_per_month`: US_GC 3.0,
  Qatar 7.0, Australia 4.0, out of capacities of 8/12/7) -- both LP
  variants enforce it as a lower bound alongside the usual liquefaction/
  storage/vessel ceilings, so an origin can be forced into a
  currently-unattractive destination instead of simply being optimized
  to zero. It's illustrative (US exports skew toward more flexible FOB
  contracts, hence the lower floor; Qatar/Australia skew toward
  long-term SPAs), not sourced -- exactly the kind of knob the eventual
  dashboard should expose. It barely moves Phase 3's own baseline
  numbers below (the floors aren't binding there), but it's what turns
  Phase 5's stress tests from a clean corner solution into a more
  realistic constrained one -- see Phase 5.
- **`src/optimization.py`**: three strategies solving the same one-month
  cargo allocation problem (how many cargoes from each origin to each
  destination), evaluated against the same 2000 simulated scenarios via
  `notebooks/04_optimization_engine.ipynb`:
  - **Naive**: ships 100% of each origin's capacity to whichever
    destination has the higher headline price, ignoring capacity
    entirely. Result: demands 27 cargoes into a 15-cargo Asia storage
    limit and 747 vessel-days against a 300-day fleet budget -- both
    oversubscribed. Once clipped to what's physically deliverable, its
    "value" drops **60%** (from a theoretical $1.33B/month to an
    achievable $534M/month) -- the naive rule's headline number is
    largely illusory.
  - **Expected-value LP**: maximizes expected netback subject to
    liquefaction/storage/**vessel-fleet** capacity (PuLP). Finds a
    genuinely non-obvious allocation: US Gulf Coast sells **domestically**
    rather than exporting, because the vessel fleet -- not liquefaction
    capacity -- is the true binding constraint, and US_GC's routes are
    vessel-day-expensive (long transits) relative to Qatar's and
    Australia's short ones; freeing the fleet for those cheaper-to-serve
    routes beats also exporting US_GC's cargoes. Delivers **$845M/month**
    -- 58% more than the naive rule's achievable value.
  - **Risk-aware LP**: maximizes `E[netback] - lambda * CVaR_95(loss)`
    via the standard Rockafellar-Uryasev LP formulation (kept as a true
    LP, not a variance penalty, which would need a quadratic objective).
    At `lambda=2.0`, reallocates Qatar's exports from mostly-Asia to
    mostly-Europe, trading **2.3% of expected value** ($845M -> $826M)
    for a **4.8% better CVaR95** ($538M -> $563M) -- a real, quantified
    risk-return tradeoff traced out as a full mean-CVaR efficient
    frontier in the notebook, exactly what a dashboard's "risk
    tolerance" slider would move along.
  - This is the direct, quantified answer to the aims doc's central
    question: naive costs you ~60% to infeasibility, and even feasible
    optimization without risk-awareness leaves a real (if smaller)
    downside-protection gap on the table.
  - Results saved to `data/processed/optimization/`.

## Status: Phase 2 (netback calculator) -- built

- **`src/netback.py`**: `compute_netback()` and
  `compute_netback_all_destinations()` implement
  `Netback = P_dest - C_shipping - C_liquefaction - C_variable - C_hedging`
  for any origin/destination pair in `network_config.py`. Freight cost
  is picked by destination basin (Europe -> Atlantic day-rate, Asia ->
  Pacific day-rate) scaled by that lane's own round-trip voyage days --
  the same rule documented for the Qatar-lane fallback, generalized to
  apply uniformly rather than as a special case.
- **`notebooks/03_netback_calculator.ipynb`**: computes netback from
  every origin to every reachable destination, first on the latest real
  prices, then across 2000 simulated 6-month-ahead scenarios from
  Phase 1's calibrator. At today's snapshot Asia wins for every origin
  on both headline price and netback (no ranking flip) -- but across
  simulated scenarios, **Europe wins 28-38% of the time depending on
  origin**, showing the "best" destination is a probability that shifts
  with the TTF-JKM spread, not a fixed answer -- exactly what Phase 3's
  risk-aware LP will need to weigh, and a stronger demonstration of the
  aims doc's core point than any single cherry-picked snapshot.
- All cost assumptions (liquefaction, variable, hedging, FX, port days)
  are illustrative placeholders in `CostAssumptions` -- exactly the
  knobs the eventual dashboard will expose as sliders.

## Status: Phase 1 (price/shipping scenario engine) -- all hubs on real data

- **Simulator built** (`src/simulator.py`): correlated mean-reverting
  jump-diffusion across 5 hubs -- Henry Hub, TTF, JKM, and freight split
  into Atlantic (Spark30S) and Pacific (Spark25S) lanes -- calibrated via
  `notebooks/02_calibrate_and_simulate.ipynb` on **real historical data
  for every hub** (no placeholders remain):
  - Henry Hub: EIA bulk file, monthly spot, 1997-2026.
  - TTF: real monthly series, 1992-2026 (`data/raw/external/`).
  - JKM: Japan LNG import price used as a proxy (not official Platts
    JKM), monthly, 1992-2026.
  - Freight: a Spark30S/25S proxy dataset (explicitly not verified
    against Spark Commodities' own values), daily, 2024-2026.
  - Calibrated on a **2021-onward "recent regime"** window rather than
    full history, since 30-year averages pull TTF/JKM reversion targets
    down to pre-boom levels no longer representative -- full-history
    numbers are kept for reference.
  - **TTF data quality issue found and fixed**: the supplied TTF file's
    2023+ values were ~3x below independently-verified real levels
    (JKM's file checked out fine by contrast). Per direction, pre-2023
    values are kept and 2023+ is reconstructed from documented anchor
    points -- clearly flagged as reconstructed, not observed, in both
    the notebook and a `ttf_is_reconstructed` column in the saved data.
  - Cross-hub correlation: TTF-JKM is set to a documented **0.70**
    rather than trusted empirically, since the correlation window falls
    entirely inside TTF's reconstructed segment (independent synthetic
    noise there drove the raw empirical estimate *negative*, contradicting
    every independent source's ~0.77-0.93). Other entries (Henry Hub
    near-zero to both TTF and JKM, freight slightly negatively correlated
    with gas prices) are left as computed.
  - Coverage checks: Henry Hub/TTF/JKM land in a reasonable 79-89% range
    against a 90% target. **Freight is under-covered (~65% at 3-6
    months)** -- a direct, visible consequence of only 32 monthly
    observations (the jump-detection threshold found zero jumps despite
    freight's obviously choppy real behavior). Flagged explicitly in the
    notebook as a known limitation, not smoothed over.
  - Calibrated parameters saved to
    `data/processed/calibration/hub_params.json`; the aligned monthly
    dataset to `data/processed/combined/monthly_aligned.csv`.

## Status: Phase 0 (setup + data access) -- complete

- Project scaffold and network structure are in place
  (`src/network_config.py`): 3 origins (US Gulf Coast, Qatar, Australia),
  Europe/Asia export destinations, plus a US-domestic outlet reachable
  only from the US origin.
- **No API key needed anywhere in this project.** Henry Hub spot/futures
  and US storage come from EIA's bulk Natural Gas download (a local
  file, no API calls) via
  [`notebooks/01_parse_bulk_ng_data.ipynb`](notebooks/01_parse_bulk_ng_data.ipynb):
  Henry Hub spot (1997-present) + futures contracts 1-4 (1993/94 to
  **2024-04 only** -- discontinued in this feed after that), weekly
  working-gas storage by region + Lower-48 total (2010-present), and
  monthly storage capacity by region (2013-present, summed since EIA
  doesn't publish a combined series).
- TTF, JKM, and freight now have real (or proxy) historical data in
  hand -- see [`docs/DATA_ACCESS.md`](docs/DATA_ACCESS.md) for the full
  picture, including the Qatar-lane freight fallback (no dedicated
  index exists; apply the same-basin day-rate scaled by that lane's own
  voyage length).

## Layout

```
src/                     core library code (network config, netback calc, LP models)
notebooks/               analysis notebooks (data checks, calibration, results)
dashboard/               Streamlit app
docs/                    writeups (data access, calibration notes)
data/raw/                untracked raw downloads (e.g. EIA bulk file)
data/processed/<source>/ untracked cleaned series, one subfolder per data source
data/checks/             untracked diagnostic output (data-access check reports)
```

## Setup

```
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# download the EIA Natural Gas bulk file from https://www.eia.gov/opendata/bulkfiles.htm
# and save it as data/raw/NG.txt, then:
jupyter notebook notebooks/01_parse_bulk_ng_data.ipynb

# once the calibration notebooks (01-02) have been run at least once:
streamlit run dashboard/app.py
```
