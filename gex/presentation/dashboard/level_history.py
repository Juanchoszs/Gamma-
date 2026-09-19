"""Plotly renderer for the backend-owned historical level payload."""
from __future__ import annotations

import plotly.graph_objects as go

from gex.presentation.dashboard.chart_theme import INSTITUTIONAL_THEME

_PALETTE = INSTITUTIONAL_THEME.colors
_COLORS = {
    "CALL_WALL": _PALETTE.call_wall,
    "PUT_WALL": _PALETTE.put_wall,
    "GAMMA_FLIP": _PALETTE.gamma_flip,
    "GEX_WALL": _PALETTE.info,
    "POC": _PALETTE.gamma_flip,
    "VAH": _PALETTE.session_regular,
    "VAL": _PALETTE.session_regular,
    "OVH": _PALETTE.session_overnight,
    "OVL": _PALETTE.session_overnight,
    "VOLUME_NODE": _PALETTE.level_neutral,
    "OI_NODE": _PALETTE.level_neutral,
}


def build_level_history_figure(payload: dict | None, level_types: list[str] | None = None) -> go.Figure:
    fig = go.Figure()
    selected_types = set(level_types or ())
    series_items = [
        item for item in (payload or {}).get("series", [])
        if not selected_types or item.get("type") in selected_types
    ]
    if not payload or not series_items:
        fig.add_annotation(text="No saved level history for this session.", showarrow=False,
                           font={"color": _PALETTE.text_secondary, "size": 13})
        fig.update_layout(height=560, paper_bgcolor=_PALETTE.background, plot_bgcolor=_PALETTE.background,
                          xaxis={"visible": False}, yaxis={"visible": False})
        return fig
    for series in series_items:
        points = series["points"]
        color = _COLORS.get(series["type"], _PALETTE.text_secondary)
        fig.add_trace(go.Scatter(
            x=[point["timestamp"] for point in points],
            y=[point["price"] for point in points],
            mode="lines+markers", name=series["id"].replace("_", " "),
            line={"color": color, "width": 1.8}, marker={"size": 5, "color": color},
            customdata=[[
                point["strength"], point.get("open_interest"), point.get("volume"), point["status"], point.get("gamma"),
            ] for point in points],
            hovertemplate=("<b>%{fullData.name}</b><br>%{x|%Y-%m-%d %H:%M}<br>"
                           "Price: %{y:,.2f}<br>Strength: %{customdata[0]}/100<br>"
                           "OI: %{customdata[1]:,.0f}<br>Volume: %{customdata[2]:,.0f}<br>"
                           "Gamma: %{customdata[4]:,.0f}<br>Status: %{customdata[3]}<extra></extra>"),
        ))
    spot = payload.get("spot", [])
    if spot:
        fig.add_trace(go.Scatter(
            x=[point["timestamp"] for point in spot], y=[point["price"] for point in spot],
            mode="lines", name="SPOT", line={"color": _PALETTE.spot, "width": 2.2},
            hovertemplate="<b>Spot</b><br>%{x|%Y-%m-%d %H:%M}<br>%{y:,.2f}<extra></extra>",
        ))
    fig.update_layout(
        title={"text": "Level history", "x": 0.01, "xanchor": "left", "font": {"size": 13, "color": _PALETTE.text_primary}},
        height=560, paper_bgcolor=_PALETTE.background, plot_bgcolor=_PALETTE.background,
        margin={"l": 58, "r": 20, "t": 48, "b": 42}, hovermode="x unified",
        legend={"orientation": "h", "y": 1.12, "x": 1, "xanchor": "right", "font": {"color": _PALETTE.text_secondary, "size": 10}},
        font={"family": INSTITUTIONAL_THEME.fonts.ui, "color": _PALETTE.text_secondary},
        xaxis={"gridcolor": _PALETTE.grid, "linecolor": _PALETTE.axis, "showspikes": True},
        yaxis={"title": "Price", "gridcolor": _PALETTE.grid, "linecolor": _PALETTE.axis, "showspikes": True},
    )
    return fig
