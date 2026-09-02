"""Chart utility functions for GEX Dashboard.

Provides helper functions for chart construction, empty states,
and data validation.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd
import plotly.graph_objects as go

from .chart_theme import (
    C,
    FONT,
    apply_market_theme,
    format_financial_value,
    market_chart_layout,
)


def empty_fig(
    msg: str,
    title: str = "",
    context: dict[str, Any] | None = None,
) -> go.Figure:
    """Create an empty chart with contextual information.

    Unlike the basic empty state, this provides clear context about:
    - What date/timeframe was selected
    - Which symbol is being analyzed
    - Whether data genuinely doesn't exist or there's a filtering issue
    - Current mode (live vs historical)

    Parameters:
        msg: Primary message to display
        title: Chart title
        context: Optional dict with additional context:
            - date: Selected date (str)
            - symbol: Current symbol (str)
            - mode: Current mode ("live" or "historical")
            - timeframe: Selected timeframe (str)
            - data_status: Specific data status ("no_data", "filtering", "error")

    Returns:
        Styled empty figure
    """
    fig = go.Figure()
    fig.update_layout(**market_chart_layout(title))
    fig = apply_market_theme(fig)

    # Build detailed message with context
    display_msg = msg

    if context:
        details = []
        if "date" in context:
            details.append(f"Date: {context['date']}")
        if "symbol" in context:
            details.append(f"Symbol: {context['symbol']}")
        if "mode" in context:
            details.append(f"Mode: {context['mode'].title()}")
        if "timeframe" in context:
            details.append(f"Range: {context['timeframe']}")

        if details:
            display_msg = f"{msg}\n\n" + "\n".join(details)

    fig.add_annotation(
        text=display_msg,
        showarrow=False,
        font=dict(color=C["muted"], size=13),
        xref="paper",
        yref="paper",
        x=0.5,
        y=0.5,
        xanchor="center",
        yanchor="middle",
    )

    return fig


def validate_chart_data(
    df: pd.DataFrame,
    context: dict[str, Any],
) -> tuple[bool, str | None]:
    """Validate data before chart rendering.

    Checks for common data issues and returns appropriate error messages.

    Parameters:
        df: DataFrame to validate
        context: Context dict for error messages

    Returns:
        (is_valid, error_message) tuple
    """
    if df is None or df.empty:
        return False, "No data available"

    # Check for required columns
    required_cols = context.get("required_columns", [])
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        return False, f"Missing required columns: {', '.join(missing_cols)}"

    # Check for valid timestamps
    if "timestamp" in df.columns:
        if df["timestamp"].isna().all():
            return False, "All timestamps are invalid"

    # Check for reasonable data ranges
    if "value" in context:
        min_val, max_val = context["value"]
        value_col = context.get("value_column", "value")
        if value_col in df.columns:
            if df[value_col].min() < min_val or df[value_col].max() > max_val:
                return False, f"Values outside expected range [{min_val}, {max_val}]"

    return True, None


def build_hover_template(
    fields: list[dict[str, str]],
    timestamp_format: str = "%H:%M",
) -> str:
    """Build a consistent hover template.

    Parameters:
        fields: List of dicts with "label" and "format" keys
        timestamp_format: Format for timestamp field

    Returns:
        Hover template string
    """
    template_parts = []

    for field in fields:
        label = field["label"]
        format_str = field.get("format", "{:.2f}")
        template_parts.append(f"{label}: {format_str}")

    return "<br>".join(template_parts) + "<extra></extra>"


def with_legend(layout: dict) -> dict:
    """Add legend configuration to layout.

    Places legend in top-right with sufficient margin.
    """
    layout["showlegend"] = True
    layout["margin"]["t"] = 62
    layout["legend"] = dict(
        orientation="h",
        y=1.13,
        x=1,
        xanchor="right",
        font=dict(color=C["ink2"], size=11),
        bgcolor="rgba(17,19,21,0.62)",
        bordercolor=C["line"],
        borderwidth=1
    )
    return layout


def add_reference_lines(
    fig: go.Figure,
    levels: list[dict[str, Any]],
    price_range: tuple[float, float],
) -> None:
    """Add reference lines to a chart with consistent styling.

    Parameters:
        fig: Plotly figure to modify
        levels: List of level dicts with keys:
            - value: Numeric level value
            - label: Display label
            - level_type: One of "spot", "zg", "wall", "secondary", "hvl"
            - side: "left" or "right" for label placement
        price_range: (min, max) price range for filtering
    """
    from .chart_theme import reference_line_style

    lo, hi = price_range

    for level in levels:
        value = level.get("value")
        if value is None or not (lo <= value <= hi):
            continue

        level_type = level.get("level_type", "secondary")
        style = reference_line_style(level_type)

        fig.add_hline(
            y=value,
            line_color=style["color"],
            line_dash=style["dash"],
            line_width=style["width"],
            annotation_text=(
                level["label"] if level.get("short")
                else f"{level['label']} {value:.0f}"
            ),
            annotation_font=dict(color=style["color"], size=10),
            annotation_position=f"top {level.get('side', 'right')}",
        )


def add_spot_band(
    fig: go.Figure,
    lo: float | None,
    hi: float | None,
    color: str = "rgba(137, 220, 255, 0.05)",
) -> None:
    """Add a subtle focal band around the current spot price.

    Parameters:
        fig: Plotly figure to modify
        lo: Lower bound of band
        hi: Upper bound of band
        color: Color for the band
    """
    if lo is None or hi is None:
        return
    fig.add_vrect(
        x0=lo,
        x1=hi,
        fillcolor=color,
        line_width=0,
        layer="below"
    )


def format_timestamp(
    ts: pd.Series,
    format_type: str = "intraday",
) -> pd.Series:
    """Format timestamps for display based on timeframe.

    Parameters:
        ts: Timestamp series
        format_type: One of "intraday", "daily", "weekly", "monthly"

    Returns:
        Formatted timestamp series
    """
    if format_type == "intraday":
        return ts.dt.strftime("%H:%M")
    elif format_type == "daily":
        return ts.dt.strftime("%m/%d")
    elif format_type == "weekly":
        return ts.dt.strftime("%m/%d")
    elif format_type == "monthly":
        return ts.dt.strftime("%Y-%m")
    else:
        return ts.dt.strftime("%Y-%m-%d")


def calculate_bar_width(strikes: pd.Series | list) -> float:
    """Calculate appropriate bar width for strike charts.

    Parameters:
        strikes: Array of strike prices

    Returns:
        Calculated bar width
    """
    import numpy as np

    strikes_array = np.array(strikes)
    diffs = np.diff(np.sort(np.unique(strikes_array)))
    return float(np.median(diffs)) * 0.75 if len(diffs) else 1.0


def apply_user_zoom(layout: dict, relayout: dict | None) -> None:
    """Reapply user zoom from relayout data.

    Preserves user zoom when chart refreshes.

    Parameters:
        layout: Layout dict to modify
        relayout: Relayout data from Dash callback
    """
    if not relayout:
        return

    for axe in ("yaxis", "xaxis"):
        lo = relayout.get(f"{axe}.range[0]")
        hi = relayout.get(f"{axe}.range[1]")
        if lo is not None and hi is not None:
            layout[axe]["range"] = [lo, hi]
            layout[axe]["autorange"] = False
