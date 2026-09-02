"""Unified Plotly chart theme system for GEX Dashboard.

This module provides consistent chart styling across all visualizations,
establishing a professional market-intelligence aesthetic.

Design principles:
- Data-first visual hierarchy
- Consistent color semantics
- Professional dark theme
- Clear information structure
- Market-aware axis formatting
"""
from __future__ import annotations

from typing import Any

import plotly.graph_objects as go

# Color palette - imported from main app for consistency
C = {
    "page": "#04090d",
    "app": "#070d13",
    "surface": "#0c141b",
    "surface_2": "#142733",
    "surface_strong": "#162d3d",
    "panel": "#0d151c",
    "panel_alt": "#091118",
    "ink": "#edf7ff",
    "ink2": "#d4e1ef",
    "muted": "#8da5bb",
    "line": "rgba(169,194,214,0.22)",
    "grid": "rgba(149, 176, 205, 0.20)",
    "axis": "rgba(212, 228, 240, 0.36)",
    "focus": "#89dcff",
    "accent": "#9fe5ff",
    "pos": "#48d2ff",   # Positive GEX / buy flow
    "neg": "#ff5d7d",   # Negative GEX / sell flow
    "spot": "#f2f7ff",
    "zg": "#ffc76d",    # Gamma Flip
    "lvl": "#7dd7ff",   # 0DTE GEX levels
    "hvl": "#57e1b5",   # HVL (Volume-weighted flip)
    "cw": "#7dd7ff",    # Call Wall (resistance)
    "ps": "#ff808d",    # Put Support (support)
    "d1": "#b7c8db",    # 1D bounds (expected move)
    "ok": "#57e1b5",
    "warning": "#ffc76d",
    "success": "#57e1b5",
    "neutral": "#8da5bb",
    "cat": ["#48d2ff", "#ff5d7d", "#57e1b5", "#ffc76d"],
}

FONT = 'system-ui, -apple-system, "Segoe UI", sans-serif'


def market_chart_layout(title: str, height: int = 420) -> dict:
    """Base layout for all market charts.

    Provides consistent spacing, fonts, and structural elements.
    """
    return dict(
        title=dict(
            text=title,
            font=dict(size=13, color=C["ink"], family=FONT),
            x=0.012,
            y=0.97,
            xanchor="left"
        ),
        template=None,
        paper_bgcolor=C["app"],
        plot_bgcolor=C["app"],
        font=dict(family=FONT, size=11, color=C["ink2"]),
        margin=dict(l=58, r=18, t=42, b=38),
        height=height,
        hovermode="x unified",
        dragmode="pan",
        xaxis=market_axis_layout(),
        yaxis=market_axis_layout(),
    )


def market_axis_layout() -> dict:
    """Consistent axis styling for market charts.

    Grid hierarchy: Data > Reference Levels > Price Line > Grid > Background
    """
    return dict(
        gridcolor=C["grid"],
        zerolinecolor="rgba(255,255,255,0.34)",
        linecolor=C["axis"],
        tickfont=dict(color=C["muted"]),
        showline=True,
        ticks="outside",
        ticklen=4,
        mirror=False,
        gridwidth=1,
        zerolinewidth=1,
    )


def market_hover_layout() -> dict:
    """Professional hover card styling.

    Dark background with clear label/value hierarchy.
    """
    return dict(
        bgcolor=C["surface_2"],
        bordercolor=C["accent"],
        font=dict(family=FONT, color=C["ink"], size=11),
    )


def market_legend_layout(orientation: str = "h", y_position: float = 1.13) -> dict:
    """Consistent legend styling.

    Parameters:
        orientation: "h" (horizontal) or "v" (vertical)
        y_position: Vertical position of legend
    """
    return dict(
        bgcolor="rgba(17,19,21,0.62)",
        bordercolor=C["line"],
        borderwidth=1,
        font=dict(color=C["ink2"], size=11),
        orientation=orientation,
        y=y_position,
        x=1,
        xanchor="right",
    )


def market_annotation_style() -> dict:
    """Consistent annotation styling for reference levels."""
    return dict(
        font=dict(color=C["ink2"], family=FONT, size=10),
    )


def apply_market_theme(fig: go.Figure) -> go.Figure:
    """Apply unified market theme to a Plotly figure.

    This ensures all charts share the same visual language:
    - Consistent colors and spacing
    - Professional grid hierarchy
    - Market-appropriate hover behavior
    - Unified trace styling
    """
    fig.update_layout(
        paper_bgcolor=C["app"],
        plot_bgcolor=C["app"],
        hoverlabel=market_hover_layout(),
        hovermode="x unified",
        dragmode="pan",
        font=dict(color=C["ink2"], family=FONT, size=11),
        bargap=0.12,
        bargroupgap=0.04,
        margin=dict(l=60, r=18, t=42, b=42),
        separators=".,",
    )

    # Apply axis styling
    fig.update_xaxes(**market_axis_layout())
    fig.update_yaxes(**market_axis_layout())

    # Apply trace-specific styling
    fig.update_traces(
        selector=dict(type="bar"),
        marker=dict(line=dict(width=1.4, color="rgba(9, 14, 19, 0.72)")),
        opacity=0.99,
    )

    fig.update_traces(
        selector=dict(type="scatter"),
        line=dict(width=2.8),
        marker=dict(size=5, line=dict(width=0.7, color="rgba(10, 15, 20, 0.82)")),
    )

    fig.update_traces(
        selector=dict(type="candlestick"),
        increasing_line=dict(color=C["pos"], width=2.5),
        decreasing_line=dict(color=C["neg"], width=2.5),
        increasing_fillcolor=C["pos"],
        decreasing_fillcolor=C["neg"],
        whiskerwidth=0.75,
        opacity=0.96,
    )

    fig.update_annotations(**market_annotation_style())

    return fig


def reference_line_style(level_type: str) -> dict[str, Any]:
    """Get styling for different reference level types.

    Creates visual hierarchy:
    - Spot: strongest
    - Gamma Flip: high importance
    - Call Wall/Put Support: medium
    - Secondary levels: subtle

    Parameters:
        level_type: One of "spot", "zg", "wall", "secondary"

    Returns:
        Dictionary with line styling parameters
    """
    styles = {
        "spot": {
            "color": C["spot"],
            "dash": "dot",
            "width": 1.5,
        },
        "zg": {
            "color": C["zg"],
            "dash": "dash",
            "width": 1.5,
        },
        "wall": {
            "color": C["cw"],  # or C["ps"] for put support
            "dash": "solid",
            "width": 1.5,
        },
        "secondary": {
            "color": C["lvl"],
            "dash": "dashdot",
            "width": 1,
        },
        "hvl": {
            "color": C["hvl"],
            "dash": "dash",
            "width": 1.5,
        },
    }
    return styles.get(level_type, styles["secondary"])


def zero_line_style() -> dict[str, Any]:
    """Special styling for zero lines in centered charts.

    Zero lines are analytically meaningful and should be distinct from grid.
    """
    return {
        "line_color": C["axis"],
        "line_width": 1,
        "line_dash": "solid",
    }


def format_financial_value(value: float, metric_type: str = "default") -> str:
    """Format financial values consistently.

    Parameters:
        value: Numeric value to format
        metric_type: Type of metric ("default", "currency", "percentage", "contracts")

    Returns:
        Formatted string
    """
    if metric_type == "currency":
        if abs(value) >= 1e9:
            return f"${value / 1e9:.2f}B"
        elif abs(value) >= 1e6:
            return f"${value / 1e6:.2f}M"
        elif abs(value) >= 1e3:
            return f"${value / 1e3:.0f}K"
        return f"${value:.0f}"
    elif metric_type == "percentage":
        return f"{value:.2f}%"
    elif metric_type == "contracts":
        if abs(value) >= 1e6:
            return f"{value / 1e6:.1f}M"
        elif abs(value) >= 1e3:
            return f"{value / 1e3:.0f}K"
        return f"{value:.0f}"
    else:
        # Default numeric formatting
        if abs(value) >= 1e9:
            return f"{value / 1e9:.2f}B"
        elif abs(value) >= 1e6:
            return f"{value / 1e6:.1f}M"
        elif abs(value) >= 1e3:
            return f"{value / 1e3:.0f}K"
        return f"{value:.2f}"


def graph_config() -> dict:
    """Consistent Plotly graph configuration.

    Removes unnecessary UI elements and enables scroll zoom.
    """
    return {
        "scrollZoom": True,
        "displaylogo": False,
        "modeBarButtonsToRemove": ["lasso2d", "select2d", "autoScale2d"],
    }
