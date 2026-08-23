"""
Phase 6: interactive Streamlit dashboard.

Ties Phases 0-5 together into a single "shock it and see" tool: a
stylized world map of the network, a sidebar shock panel (price,
freight, capacity, and route shocks, all backed by the real override
mechanisms in src/network_config.py and src/optimization.py, not a
mock), and before/after comparisons of the resulting optimal
allocation. Every shock control carries a hover tooltip (Streamlit's
native `help=`) explaining a real situation that would cause it,
per the project's running theme: directional realism over historical
precision, since this is built to be shocked, not to reproduce history.
"""

import os
import sys

import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from geo import SHOCK_INFO
from map_view import build_map_figure
from network_config import DESTINATIONS, ORIGINS
from pipeline import default_shock_params, run_scenario

st.set_page_config(page_title="LNG Flows", page_icon="\U0001F30D", layout="wide")

st.markdown(
    """
    <style>
    .stApp { background-color: #0e1420; color: #e8edf4; }
    section[data-testid="stSidebar"] { background-color: #131b28; }
    div[data-testid="stMetric"] {
        background-color: #161f2e; border: 1px solid #263244;
        border-radius: 10px; padding: 12px 16px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("LNG Flows -- Network Shock Dashboard")
st.caption(
    "3 origins, 3 destinations, one calibrated Monte Carlo price model, two optimization strategies. "
    "Shock a price, a capacity, or a route in the sidebar and see how the optimal allocation reshuffles."
)

ORIGIN_KEYS = list(ORIGINS.keys())
DEST_KEYS = list(DESTINATIONS.keys())

with st.sidebar:
    st.header("⚡ Shock Panel")
    st.caption("Adjust, then press **Apply Shock** to re-solve both LPs under the new scenario.")

    with st.form("shock_form"):
        st.subheader("Price shocks")
        ttf_mult = st.slider("TTF (Europe) price x", 0.5, 2.5, 1.0, 0.05, help=SHOCK_INFO["ttf"])
        jkm_mult = st.slider("JKM (Asia) price x", 0.5, 2.5, 1.0, 0.05, help=SHOCK_INFO["jkm"])

        st.subheader("Freight shocks")
        freight_atl_mult = st.slider("Atlantic freight day-rate x", 0.5, 3.0, 1.0, 0.05, help=SHOCK_INFO["freight_atlantic"])
        freight_pac_mult = st.slider("Pacific freight day-rate x", 0.5, 3.0, 1.0, 0.05, help=SHOCK_INFO["freight_pacific"])

        st.subheader("Route disruptions")
        suez_days = st.slider("Suez/Cape reroute: extra days (Qatar->Europe)", 0.0, 20.0, 0.0, 0.5, help=SHOCK_INFO["suez"])
        panama_days = st.slider("Panama disruption: extra days (US_GC->Asia)", 0.0, 20.0, 0.0, 0.5, help=SHOCK_INFO["panama"])

        st.subheader("Storage capacity")
        storage_pct = {}
        storage_pct["EUROPE"] = st.slider("Europe storage capacity %", 0, 150, 100, 5, help=SHOCK_INFO["europe_storage"])
        storage_pct["ASIA"] = st.slider("Asia storage capacity %", 0, 150, 100, 5, help=SHOCK_INFO["asia_storage"])
        storage_pct["US_DOMESTIC"] = st.slider("US domestic outlet capacity %", 0, 150, 100, 5, help=SHOCK_INFO["us_domestic_storage"])

        st.subheader("Liquefaction outages")
        liquefaction_pct = {}
        for key in ORIGIN_KEYS:
            liquefaction_pct[key] = st.slider(f"{ORIGINS[key].name} liquefaction capacity %", 0, 100, 100, 5, help=SHOCK_INFO["liquefaction"])

        st.subheader("Take-or-pay floors")
        min_supply_pct = {}
        for key in ORIGIN_KEYS:
            min_supply_pct[key] = st.slider(f"{ORIGINS[key].name} take-or-pay floor %", 0, 150, 100, 10, help=SHOCK_INFO["min_supply"])

        st.subheader("Vessel fleet")
        vessel_pct = st.slider("Fleet size %", 0, 150, 100, 5, help=SHOCK_INFO["vessel_fleet"])

        st.subheader("Strategy")
        risk_lambda = st.slider("Risk aversion (lambda)", 0.0, 5.0, 2.0, 0.25, help=SHOCK_INFO["risk_lambda"])
        duration_months = st.slider("Shock duration (months)", 1, 12, 1, 1, help=SHOCK_INFO["duration"])

        submitted = st.form_submit_button("⚡ Apply Shock", width="stretch")

shocks = {
    "ttf_mult": ttf_mult,
    "jkm_mult": jkm_mult,
    "freight_atlantic_mult": freight_atl_mult,
    "freight_pacific_mult": freight_pac_mult,
    "liquefaction_pct": liquefaction_pct,
    "min_supply_pct": min_supply_pct,
    "storage_pct": storage_pct,
    "vessel_pct": vessel_pct,
    "suez_extra_days": suez_days,
    "panama_extra_days": panama_days,
    "risk_lambda": risk_lambda,
    "duration_months": duration_months,
}
baseline_shocks = default_shock_params()
baseline_shocks["risk_lambda"] = risk_lambda  # isolate the shock's effect from a lambda change

with st.spinner("Solving..."):
    baseline = run_scenario(baseline_shocks)
    shocked = run_scenario(shocks)

is_shock_active = any(
    [
        ttf_mult != 1.0,
        jkm_mult != 1.0,
        freight_atl_mult != 1.0,
        freight_pac_mult != 1.0,
        suez_days > 0,
        panama_days > 0,
        any(v != 100 for v in storage_pct.values()),
        any(v != 100 for v in liquefaction_pct.values()),
        any(v != 100 for v in min_supply_pct.values()),
        vessel_pct != 100,
    ]
)

if shocked["ev_status"] != "Optimal":
    st.error(
        f"This shock combination is **infeasible** (solver status: {shocked['ev_status']}) -- most likely a "
        "take-or-pay floor left above a shocked-down capacity. There is no valid allocation satisfying every "
        "constraint at once; try raising the relevant capacity back up or lowering that origin's floor. "
        "This is a genuine real-world failure mode, not a dashboard bug -- a real desk facing this would be "
        "unable to honor a contract's minimum and would need to renegotiate."
    )
else:
    b_stats, s_stats = baseline["ev_stats"], shocked["ev_stats"]
    b_util, s_util = baseline["ev_utilization"], shocked["ev_utilization"]

    st.subheader("Portfolio impact" + (" (no shock applied)" if not is_shock_active else ""))
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Expected value ($M/mo)", f"{s_stats['mean']/1e6:,.0f}", f"{(s_stats['mean']-b_stats['mean'])/1e6:+,.0f}" if is_shock_active else None)
    c2.metric("CVaR95 ($M/mo, worst 5%)", f"{s_stats['CVaR95']/1e6:,.0f}", f"{(s_stats['CVaR95']-b_stats['CVaR95'])/1e6:+,.0f}" if is_shock_active else None)
    c3.metric("Vessel fleet utilization", f"{s_util['vessel_fleet']:.0%}", f"{(s_util['vessel_fleet']-b_util['vessel_fleet'])*100:+.0f}pp" if is_shock_active else None)
    c4.metric("Worst-case shortfall", f"{s_stats['worst_case_shortfall_pct']:.0f}%", f"{s_stats['worst_case_shortfall_pct']-b_stats['worst_case_shortfall_pct']:+.0f}pp" if is_shock_active else None, delta_color="inverse")

    if is_shock_active and duration_months > 1:
        cumulative = (s_stats["mean"] - b_stats["mean"]) * duration_months
        st.metric(
            f"Approximate cumulative impact over {duration_months} months",
            f"${cumulative/1e6:+,.0f}M",
            help=SHOCK_INFO["duration"],
        )

    st.divider()

    map_col, table_col = st.columns([2, 1])
    with map_col:
        st.subheader("Network map" + (" -- after shock" if is_shock_active else ""))
        active_result = shocked if is_shock_active else baseline
        fig = build_map_figure(
            active_result["ev_allocation"],
            active_result["netbacks"],
            active_result["origins"],
            active_result["destinations"],
            active_result["ev_utilization"],
        )
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
        st.caption(
            "Node color: amber = origin, blue = destination. Node size scales with utilization. "
            "Link width scales with cargoes shipped; link color scales red (low netback) to green (high netback). "
            "Hover any node or link for details."
        )

    with table_col:
        st.subheader("Allocation (cargoes/month)")
        strategy = st.radio("Strategy", ["Expected-value LP", "Risk-aware LP"], horizontal=True, label_visibility="collapsed")
        alloc = shocked["ev_allocation"] if strategy == "Expected-value LP" else shocked["risk_allocation"]
        if alloc is None:
            st.warning(f"Risk-aware LP did not solve to optimality (status: {shocked['risk_status']}).")
        else:
            rows = [{"route": f"{o} -> {d}", "cargoes": round(q, 2)} for (o, d), q in sorted(alloc.items()) if q and q > 0.005]
            st.dataframe(rows, hide_index=True, width="stretch")

    with st.expander("ℹ️ About this model"):
        st.markdown(
            """
            - Prices/freight are simulated from a correlated mean-reverting jump-diffusion calibrated on
              real historical data (Phase 1); shocks here are applied as multipliers on top of that
              simulated distribution, not a re-calibration.
            - Both strategies solve a **single representative month** -- the "duration" control scales the
              displayed cumulative dollar impact as a simple approximation, not a re-simulated multi-month path.
            - Capacity, cost, and take-or-pay figures throughout are illustrative placeholders sized to a
              plausible order of magnitude, not sourced data -- see the project README for details.
            - This dashboard is built to explore *direction and magnitude of response to shocks*, not to
              reproduce history precisely.
            """
        )
