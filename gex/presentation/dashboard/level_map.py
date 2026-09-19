"""Plotly renderer for normalized unified market levels."""
from __future__ import annotations

import plotly.graph_objects as go

from collections.abc import Iterable

from gex.application.market_intelligence.service import MarketIntelligenceSnapshot
from gex.domain.market.intelligence import MarketLevel
from gex.presentation.dashboard.chart_theme import INSTITUTIONAL_THEME


_THEME = INSTITUTIONAL_THEME
_PALETTE = _THEME.colors
_COLORS = {
    "PUT_WALL": _PALETTE.put, "CALL_WALL": _PALETTE.call, "GEX_WALL": _PALETTE.info,
    "GAMMA_FLIP": _PALETTE.gamma_flip, "POC": _PALETTE.gamma_flip,
    "VAH": _PALETTE.session_regular, "VAL": _PALETTE.session_regular,
    "OVH": _PALETTE.session_overnight, "OVL": _PALETTE.session_overnight,
    "HIGH_GAMMA": _PALETTE.positive, "LOW_GAMMA": _PALETTE.negative,
    "VOLUME_NODE": _PALETTE.info, "OI_NODE": _PALETTE.level_neutral,
}


def build_level_map_figure(
    snapshot: MarketIntelligenceSnapshot | None,
    levels: Iterable[MarketLevel] | None = None,
) -> go.Figure:
    """Map backend-provided level price and strength without ranking again."""
    fig = go.Figure()
    visible_levels = tuple(levels) if levels is not None else (snapshot.report.key_levels if snapshot else ())
    if snapshot is None or not visible_levels:
        fig.add_annotation(text="No unified levels are available.", showarrow=False,
                           font={"color": _PALETTE.text_secondary, "size": 13})
        fig.update_layout(height=500, paper_bgcolor=_PALETTE.background, plot_bgcolor=_PALETTE.background,
                          xaxis={"visible": False}, yaxis={"visible": False})
        return fig
    levels = visible_levels
    fig.add_trace(go.Scatter(
        x=[level.strength for level in levels], y=[level.price for level in levels],
        mode="markers+text", text=[level.level_type.value.replace("_", " ") for level in levels],
        textposition="middle right", textfont={"size": 10, "color": _PALETTE.text_primary},
        marker={"size": 10, "color": [_COLORS.get(level.level_type.value, _PALETTE.level_neutral) for level in levels]},
        customdata=[[level.source.value, level.session.value, level.status.value, level.distance_percent]
                    for level in levels],
        hovertemplate=("<b>%{text}</b><br>Price: %{y:,.2f}<br>Strength: %{x}/100<br>"
                       "Source: %{customdata[0]}<br>Session: %{customdata[1]}<br>"
                       "Status: %{customdata[2]}<br>Distance: %{customdata[3]:+.2f}%<extra></extra>"),
        name="Unified levels",
    ))
    fig.add_hline(y=snapshot.state.spot, line={"color": _PALETTE.spot, "width": 2}, annotation_text="SPOT",
                  annotation_font={"color": _PALETTE.spot, "size": 10}, annotation_position="top left")
    fig.update_layout(
        title={"text": f"{snapshot.state.symbol} unified levels", "x": 0.01, "xanchor": "left",
               "font": {"size": 13, "color": _PALETTE.text_primary}},
        height=500, paper_bgcolor=_PALETTE.background, plot_bgcolor=_PALETTE.background,
        margin={"l": 72, "r": 135, "t": 48, "b": 45}, showlegend=False,
        font={"family": _THEME.fonts.ui, "color": _PALETTE.text_secondary},
        xaxis={
            "title": "Deterministic strength", "range": [0, 105], "gridcolor": _PALETTE.grid,
            "showspikes": True, "spikemode": "across", "spikecolor": _PALETTE.axis, "spikethickness": 1,
        },
        yaxis={
            "title": "Price", "gridcolor": _PALETTE.grid, "tickformat": ",.2f",
            "showspikes": True, "spikemode": "across", "spikecolor": _PALETTE.axis, "spikethickness": 1,
        },
    )
    return fig
