"""
Phase 6: stylized world map of the LNG network.

Deliberately NOT go.Scattergeo -- that trace type needs Plotly's JS
runtime to fetch topojson coastline data from cdn.plot.ly at render
time, which fails in a network-restricted environment (and is a fragile
external dependency for any deployment, sourced-key-free ethos aside --
see Phase 0's README section). Instead: a plain Cartesian scatter with
x=longitude, y=latitude (equirectangular / Plate Carrée) and a handful
of hand-simplified continent silhouettes drawn as filled shapes. Fully
self-contained, no network call, and arguably a better fit for
"stylized" than a literal borders-and-labels basemap.
"""

import plotly.graph_objects as go

from geo import CONTINENTS, NODE_COORDS

LAND_COLOR = "#1b2430"
LAND_LINE = "#28344a"
OCEAN_COLOR = "#0e1420"
GRID_COLOR = "#1a2334"
ORIGIN_COLOR = "#f2a154"
DEST_COLOR = "#4fa8e0"
EDGE_LOW = (200, 70, 70)   # low/negative netback -> red
EDGE_HIGH = (90, 200, 130)  # high netback -> green


def _lerp_color(t: float) -> str:
    t = max(0.0, min(1.0, t))
    r = round(EDGE_LOW[0] + (EDGE_HIGH[0] - EDGE_LOW[0]) * t)
    g = round(EDGE_LOW[1] + (EDGE_HIGH[1] - EDGE_LOW[1]) * t)
    b = round(EDGE_LOW[2] + (EDGE_HIGH[2] - EDGE_LOW[2]) * t)
    return f"rgb({r},{g},{b})"


def build_map_figure(allocation: dict, netbacks: dict, origins_cfg: dict, destinations_cfg: dict, utilization: dict) -> go.Figure:
    fig = go.Figure()

    for poly in CONTINENTS:
        lons = [p[0] for p in poly] + [poly[0][0]]
        lats = [p[1] for p in poly] + [poly[0][1]]
        fig.add_trace(
            go.Scatter(
                x=lons,
                y=lats,
                mode="lines",
                fill="toself",
                fillcolor=LAND_COLOR,
                line=dict(width=1, color=LAND_LINE),
                hoverinfo="skip",
                showlegend=False,
            )
        )

    mean_netbacks = {k: float(v.mean()) for k, v in netbacks.items()}
    active_edges = {k: v for k, v in mean_netbacks.items() if allocation.get(k, 0) and allocation[k] > 0.005}
    if active_edges:
        vmin, vmax = min(active_edges.values()), max(active_edges.values())
        spread = (vmax - vmin) or 1.0
    else:
        vmin = spread = 0.0

    max_qty = max([allocation.get(k, 0) for k in active_edges] + [1.0])

    for (origin, dest), nb in active_edges.items():
        if origin not in NODE_COORDS or dest not in NODE_COORDS:
            continue
        qty = allocation[(origin, dest)]
        o, d = NODE_COORDS[origin], NODE_COORDS[dest]
        width = 1.5 + 8.0 * (qty / max_qty)
        color = _lerp_color((nb - vmin) / spread if spread else 1.0)
        fig.add_trace(
            go.Scatter(
                x=[o["lon"], d["lon"]],
                y=[o["lat"], d["lat"]],
                mode="lines",
                line=dict(width=width, color=color),
                opacity=0.85,
                hoverinfo="text",
                hovertext=f"{o['label']} -> {d['label']}<br>{qty:.2f} cargoes/month<br>netback ${nb:.2f}/MMBtu",
                showlegend=False,
            )
        )

    for key, cfg in {**origins_cfg, **destinations_cfg}.items():
        if key not in NODE_COORDS:
            continue
        node = NODE_COORDS[key]
        is_origin = node["kind"] == "origin"
        color = ORIGIN_COLOR if is_origin else DEST_COLOR
        if is_origin:
            util = utilization["liquefaction_by_origin"].get(key, 0.0)
            cap_line = f"Liquefaction capacity: {cfg.liquefaction_capacity_cargoes_per_month:.1f} cargoes/mo"
            floor_line = f"Take-or-pay floor: {cfg.min_supply_cargoes_per_month:.1f} cargoes/mo"
            hover = f"<b>{node['label']}</b><br>{cap_line}<br>{floor_line}<br>Utilization: {util:.0%}"
        else:
            util = utilization["storage_by_destination"].get(key, 0.0)
            cap_line = f"Storage capacity: {cfg.storage_capacity_cargoes:.1f} cargoes/mo"
            hover = f"<b>{node['label']}</b><br>{cap_line}<br>Utilization: {util:.0%}"

        size = 20 + 16 * min(util, 1.0)
        fig.add_trace(
            go.Scatter(
                x=[node["lon"]],
                y=[node["lat"]],
                mode="markers+text",
                marker=dict(size=size, color=color, line=dict(width=1.5, color="#0e1420"), opacity=0.95),
                text=[node["label"]],
                textposition="bottom center",
                textfont=dict(color="#e8edf4", size=11),
                hoverinfo="text",
                hovertext=hover,
                showlegend=False,
            )
        )

    axis_common = dict(
        showgrid=True, gridcolor=GRID_COLOR, zeroline=False, showticklabels=False,
        fixedrange=True,
    )
    fig.update_layout(
        paper_bgcolor=OCEAN_COLOR,
        plot_bgcolor=OCEAN_COLOR,
        margin=dict(l=0, r=0, t=10, b=0),
        height=520,
        font=dict(color="#e8edf4"),
        xaxis=dict(**axis_common, range=[-170, 165]),
        yaxis=dict(**axis_common, range=[-52, 75], scaleanchor="x", scaleratio=1),
        hovermode="closest",
    )
    return fig
