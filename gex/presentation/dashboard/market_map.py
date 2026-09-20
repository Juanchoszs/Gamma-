"""Plotly renderer for the normalized market-map payload."""
from __future__ import annotations

import plotly.graph_objects as go

from gex.presentation.dashboard.chart_theme import INSTITUTIONAL_THEME


_COLORS = INSTITUTIONAL_THEME.colors
_DECISION_LEVEL_TYPES = ("CALL_WALL", "PUT_WALL", "GAMMA_FLIP")
_ANNOTATION_SHIFT = {"CALL_WALL": 14, "GAMMA_FLIP": -14, "PUT_WALL": 0}


def _decision_levels(levels: list[dict]) -> list[dict]:
    """Keep the price map readable by labeling only its three decision anchors."""
    selected = []
    for level_type in _DECISION_LEVEL_TYPES:
        candidates = [
            level for level in levels
            if level.get("type") == level_type and level.get("price") is not None
        ]
        if candidates:
            selected.append(max(candidates, key=lambda level: int(level.get("strength", 0) or 0)))
    return selected


def build_market_map_figure(payload: dict | None) -> go.Figure:
    """Draw backend exposure rows and unified levels without recomputation."""
    fig = go.Figure()
    if not payload or not payload.get("rows"):
        fig.add_annotation(text="No market-map rows are available.", showarrow=False,
                           font={"color": _COLORS.text_secondary, "size": 13})
        fig.update_layout(height=620, paper_bgcolor=_COLORS.background, plot_bgcolor=_COLORS.background,
                          xaxis={"visible": False}, yaxis={"visible": False})
        return fig

    rows = payload["rows"]
    strikes = [row["strike"] for row in rows]
    fig.add_trace(go.Bar(
        name="Call GEX", x=[row["call_gex"] for row in rows], y=strikes,
        orientation="h", marker={"color": _COLORS.call},
        customdata=[[row["call_open_interest"], row["call_volume"], row["distance_percent"]] for row in rows],
        hovertemplate=("<b>Call GEX</b><br>Strike: %{y:,.2f}<br>GEX: %{x:,.0f}<br>"
                       "OI: %{customdata[0]:,.0f}<br>Volume: %{customdata[1]:,.0f}<br>"
                       "Distance: %{customdata[2]:+.2f}%<extra></extra>"),
    ))
    fig.add_trace(go.Bar(
        name="Put GEX", x=[row["put_gex"] for row in rows], y=strikes,
        orientation="h", marker={"color": _COLORS.put},
        customdata=[[row["put_open_interest"], row["put_volume"], row["distance_percent"]] for row in rows],
        hovertemplate=("<b>Put GEX</b><br>Strike: %{y:,.2f}<br>GEX: %{x:,.0f}<br>"
                       "OI: %{customdata[0]:,.0f}<br>Volume: %{customdata[1]:,.0f}<br>"
                       "Distance: %{customdata[2]:+.2f}%<extra></extra>"),
    ))
    spot = float(payload["spot"])
    fig.add_hline(y=spot, line={"color": _COLORS.spot, "width": 2}, annotation_text="SPOT",
                  annotation_font={"color": _COLORS.spot, "size": 10}, annotation_position="top left")
    for level in _decision_levels(payload.get("levels", [])):
        price = level.get("price")
        if price is None:
            continue
        level_type = str(level.get("type", "LEVEL"))
        fig.add_hline(
            y=float(price), line={"color": _level_color(level_type), "width": 1, "dash": "dot"},
            annotation_text=level_type.replace("_", " "),
            annotation_font={"color": _level_color(level_type), "size": 9},
            annotation_position="top right",
            annotation_yshift=_ANNOTATION_SHIFT.get(level_type, 0),
        )
    fig.update_layout(
        title={"text": f"{payload.get('symbol', 'Market')} exposure by strike", "x": 0.01,
               "xanchor": "left", "font": {"size": 13, "color": _COLORS.text_primary}},
        barmode="relative", height=620, paper_bgcolor=_COLORS.background, plot_bgcolor=_COLORS.background,
        margin={"l": 72, "r": 120, "t": 48, "b": 46}, hovermode="closest",
        legend={"orientation": "h", "y": 1.11, "x": 1, "xanchor": "right",
                "font": {"color": _COLORS.text_secondary, "size": 10}},
        font={"family": INSTITUTIONAL_THEME.fonts.ui, "color": _COLORS.text_secondary},
        xaxis={
            "title": "Gamma exposure", "gridcolor": _COLORS.grid, "zerolinecolor": _COLORS.axis,
            "showspikes": True, "spikemode": "across", "spikecolor": _COLORS.axis, "spikethickness": 1,
        },
        yaxis={
            "title": "Strike", "gridcolor": _COLORS.grid, "linecolor": _COLORS.axis, "tickformat": ",.0f",
            "showspikes": True, "spikemode": "across", "spikecolor": _COLORS.axis, "spikethickness": 1,
        },
    )
    return fig


def _level_color(level_type: str) -> str:
    if level_type == "HIGH_GAMMA":
        return _COLORS.positive
    if level_type == "LOW_GAMMA":
        return _COLORS.negative
    if "PUT" in level_type or level_type in {"VAL", "OVL"}:
        return _COLORS.put
    if "CALL" in level_type or level_type in {"VAH", "OVH"}:
        return _COLORS.call
    if "FLIP" in level_type:
        return _COLORS.gamma_flip
    return _COLORS.info
