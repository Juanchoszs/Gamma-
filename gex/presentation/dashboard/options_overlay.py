"""Price candles with live GEX levels for the dashboard's primary strike map.

The module deliberately only renders data prepared by the application layer:
it never calculates gamma or reads a market-data provider. OHLC bars are the
only source for the candles; when they are unavailable the chart reports that
state rather than manufacturing a price history from option snapshots.
"""
from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from datetime import datetime

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from gex.application.options_flow.dto import GEXLevel, OptionsOverlayViewModel
from gex.application.options_flow.service import FlowBubble
from gex.domain.options.models import FlowAggressiveness, FlowSide, OptionType
from gex.presentation.dashboard.chart_animations import animation_engine

log = logging.getLogger(__name__)

COLORS = {
    "surface": "#0b1118",
    "card": "#101923",
    "ink": "#f4f7fb",
    "muted": "#a8b3c2",
    "grid": "#17232e",
    "up": "#2dd4bf",
    "down": "#f05c7c",
    "spot": "#f4f7fb",
    "call_wall": "#22d3ee",
    "call_wall_glow": "rgba(34, 211, 238, 0.22)",
    "put_wall": "#f05c7c",
    "put_wall_glow": "rgba(240, 92, 124, 0.22)",
    "flip": "#f6c85f",
    "flip_glow": "rgba(246, 200, 95, 0.18)",
    "call_flow": "#2dd4bf",
    "call_flow_passive": "rgba(45, 212, 191, 0.52)",
    "put_flow": "#f05c7c",
    "put_flow_passive": "rgba(240, 92, 124, 0.52)",
}


def _fmt_gex(val: float) -> str:
    sign = "+" if val > 0 else "-" if val < 0 else ""
    abs_v = abs(val)
    if abs_v >= 1e9:
        return f"{sign}${abs_v / 1e9:.2f}B"
    if abs_v >= 1e6:
        return f"{sign}${abs_v / 1e6:.2f}M"
    if abs_v >= 1e3:
        return f"{sign}${abs_v / 1e3:.1f}K"
    return f"{sign}${abs_v:.0f}"


def _empty(message: str) -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(
        text=message, showarrow=False,
        font=dict(color=COLORS["muted"], size=14, family="Inter, sans-serif"),
    )
    fig.update_layout(
        height=620, paper_bgcolor=COLORS["surface"], plot_bgcolor=COLORS["surface"],
        margin=dict(l=54, r=28, t=50, b=45),
        xaxis=dict(visible=False), yaxis=dict(visible=False),
    )
    return fig


def _wall_stats(chain: pd.DataFrame, strike: float, side: str) -> tuple[float, float, float]:
    """Return GEX, OI and volume at a level without recreating GEX maths."""
    rows = chain[(chain["strike"] == strike) & (chain["type"] == side)]
    if rows.empty:
        return 0.0, 0.0, 0.0
    return (
        float(rows["gex"].sum()) if "gex" in rows else 0.0,
        float(rows["open_interest"].fillna(0).sum()) if "open_interest" in rows else 0.0,
        float(rows["volume"].fillna(0).sum()) if "volume" in rows else 0.0,
    )


def _overlay_levels(
    chain: pd.DataFrame,
    spot: float,
    keys: dict,
) -> tuple[list[float], list[float]]:
    """Resolve the three directional levels without changing GEX calculation."""
    call_levels = keys.get("call_walls")
    put_levels = keys.get("put_supports")
    if isinstance(call_levels, (list, tuple)) and isinstance(put_levels, (list, tuple)):
        return list(map(float, call_levels[:3])), list(map(float, put_levels[:3]))

    if chain.empty or not {"strike", "type", "gex"}.issubset(chain.columns):
        return [], []
    grouped = chain.groupby(["type", "strike"])["gex"].sum()
    calls = grouped[(grouped.index.get_level_values("type") == "C")
                    & (grouped.index.get_level_values("strike") >= spot)
                    & (grouped > 0)]
    puts = grouped[(grouped.index.get_level_values("type") == "P")
                   & (grouped.index.get_level_values("strike") <= spot)
                   & (grouped < 0)]
    return (
        [float(strike) for strike in calls.abs().nlargest(3).index.get_level_values("strike")],
        [float(strike) for strike in puts.abs().nlargest(3).index.get_level_values("strike")],
    )


def _legacy_gex_levels(
    chain: pd.DataFrame,
    spot: float,
    gamma_flip: float | None,
    keys: dict,
    show_call_wall: bool,
    show_put_wall: bool,
    show_gamma_flip: bool,
) -> list[GEXLevel]:
    call_levels, put_levels = _overlay_levels(chain, spot, keys)
    levels: list[GEXLevel] = []
    if show_call_wall:
        for idx, price in enumerate(call_levels):
            gex, oi, volume = _wall_stats(chain, float(price), "C")
            levels.append(GEXLevel(
                name="Call Wall" if idx == 0 else f"Call Wall {idx + 1}",
                price=float(price),
                value=gex,
                side="C",
                open_interest=oi,
                volume=volume,
                color_key="call_wall",
                glow_key="call_wall_glow",
            ))
    if show_put_wall:
        for idx, price in enumerate(put_levels):
            gex, oi, volume = _wall_stats(chain, float(price), "P")
            levels.append(GEXLevel(
                name="Put Wall" if idx == 0 else f"Put Wall {idx + 1}",
                price=float(price),
                value=gex,
                side="P",
                open_interest=oi,
                volume=volume,
                color_key="put_wall",
                glow_key="put_wall_glow",
            ))
    if show_gamma_flip and gamma_flip is not None:
        nearby = chain[np.isclose(chain["strike"], float(gamma_flip))] if "strike" in chain else pd.DataFrame()
        gex = float(nearby["gex"].sum()) if "gex" in nearby else 0.0
        oi = float(nearby["open_interest"].fillna(0).sum()) if "open_interest" in nearby else 0.0
        volume = float(nearby["volume"].fillna(0).sum()) if "volume" in nearby else 0.0
        levels.append(GEXLevel(
            name="Gamma Flip",
            price=float(gamma_flip),
            value=gex,
            style="dash",
            open_interest=oi,
            volume=volume,
            color_key="flip",
            glow_key="flip_glow",
        ))
    return levels


def _level_enabled(level: GEXLevel, show_call_wall: bool, show_put_wall: bool, show_gamma_flip: bool) -> bool:
    if not level.visible:
        return False
    if level.name.startswith("Call Wall"):
        return show_call_wall
    if level.name.startswith("Put Wall"):
        return show_put_wall
    if level.name == "Gamma Flip":
        return show_gamma_flip
    return True


def _gamma_activity_points(
    snapshots: list[tuple[datetime, pd.DataFrame]] | None,
    spot: float,
    window: float,
) -> list[dict]:
    """Extract dominant positive/negative gamma strikes across intraday snapshots."""
    if not snapshots:
        return []
    points = []
    low, high = spot * (1.0 - window), spot * (1.0 + window)
    for timestamp, chain in snapshots:
        if chain is None or chain.empty or "strike" not in chain or "gex" not in chain:
            continue
        visible = chain[(chain["strike"] >= low) & (chain["strike"] <= high)]
        if visible.empty:
            continue
        for option_type in ("C", "P"):
            side = visible[visible["type"] == option_type]
            if side.empty:
                continue
            ordered = side.sort_values("gex", ascending=(option_type == "P"))
            lead = ordered.iloc[0]
            points.append({
                "timestamp": timestamp,
                "type": option_type,
                "strike": float(lead["strike"]),
                "gex": float(lead["gex"]),
                "open_interest": float(lead.get("open_interest", 0.0) or 0.0),
                "volume": float(lead.get("volume", 0.0) or 0.0),
            })
    return points


def _add_gamma_activity(
    fig: go.Figure,
    points: list[dict],
    transform: Callable[[float], float],
) -> None:
    if not points:
        return
    stamps = sorted({point["timestamp"] for point in points})
    next_timestamp = {stamps[idx]: (stamps[idx + 1] if idx + 1 < len(stamps) else stamps[idx])
                      for idx in range(len(stamps))}
    largest = max((abs(point["gex"]) for point in points), default=1.0) or 1.0
    specs = (("C", "Active call GEX", COLORS["call_wall"]),
             ("P", "Active put GEX", COLORS["put_wall"]))
    for option_type, name, color in specs:
        side = [point for point in points if point["type"] == option_type]
        if not side:
            continue
        rail_x: list[object] = []
        rail_y: list[object] = []
        for point in side:
            end = next_timestamp[point["timestamp"]]
            if end == point["timestamp"]:
                continue
            rail_x.extend([point["timestamp"], end, None])
            shown_strike = float(transform(point["strike"]))
            rail_y.extend([shown_strike, shown_strike, None])
        if rail_x:
            fig.add_trace(go.Scatter(
                x=rail_x, y=rail_y, mode="lines", name=name,
                line=dict(color=color, width=3), opacity=0.45, hoverinfo="skip",
                legendgroup=f"activity-{option_type}",
            ))
        custom = np.asarray([[point["gex"], point["open_interest"], point["volume"]]
                             for point in side])
        sizes = [8 + 14 * np.sqrt(abs(point["gex"]) / largest) for point in side]
        fig.add_trace(go.Scatter(
            x=[point["timestamp"] for point in side],
            y=[float(transform(point["strike"])) for point in side],
            mode="markers", name=f"{name} points", showlegend=False,
            marker=dict(size=sizes, color=color, opacity=0.88,
                        line=dict(color=COLORS["surface"], width=1.5)),
            customdata=custom, legendgroup=f"activity-{option_type}",
            hovertemplate=(
                f"<b style='color:{color}'>● {name}</b><br>"
                "Snapshot: <b>%{x|%H:%M:%S}</b><br>"
                "Strike: <b>%{y:,.2f}</b><br>"
                "GEX: %{customdata[0]:+,.0f}<br>"
                "Open interest: %{customdata[1]:,.0f}<br>"
                "Volume: %{customdata[2]:,.0f}<extra></extra>"
            ),
        ))


def _fmt_money(value: float | None) -> str:
    if value is None:
        return ""
    abs_v = abs(value)
    sign = "-" if value < 0 else ""
    if abs_v >= 1e9:
        return f"{sign}${abs_v / 1e9:.2f}B"
    if abs_v >= 1e6:
        return f"{sign}${abs_v / 1e6:.2f}M"
    if abs_v >= 1e3:
        return f"{sign}${abs_v / 1e3:.1f}K"
    return f"{sign}${abs_v:,.0f}"


def _flow_marker_color(bubble: FlowBubble) -> str:
    if bubble.option_type is OptionType.CALL:
        return COLORS["call_flow"] if bubble.side is not FlowSide.SELL else COLORS["call_flow_passive"]
    return COLORS["put_flow"] if bubble.side is not FlowSide.SELL else COLORS["put_flow_passive"]


def _bubble_customdata(bubbles: list[FlowBubble]) -> np.ndarray:
    return np.asarray([
        [
            bubble.option_type.value,
            bubble.premium,
            bubble.volume,
            bubble.event_count,
            bubble.average_price if bubble.average_price is not None else np.nan,
            bubble.open_interest if bubble.open_interest is not None else np.nan,
            bubble.implied_volatility if bubble.implied_volatility is not None else np.nan,
            bubble.gamma if bubble.gamma is not None else np.nan,
            bubble.delta if bubble.delta is not None else np.nan,
            bubble.side.value,
            _fmt_money(bubble.premium),
        ]
        for bubble in bubbles
    ], dtype=object)


def _flow_hover_text(bubble: FlowBubble) -> str:
    lines = [
        f"<b>{bubble.option_type.value} Flow</b>",
        f"Strike: <b>{bubble.strike:,.2f}</b>",
        f"Premium: <b>{_fmt_money(bubble.premium)}</b>",
        f"Volume: {bubble.volume:,.0f}",
        f"Events: {bubble.event_count:,.0f}",
    ]
    if bubble.average_price is not None:
        lines.append(f"Avg price: {bubble.average_price:,.2f}")
    if bubble.expiration is not None:
        lines.append(f"Expiration: {bubble.expiration:%Y-%m-%d}")
    if bubble.open_interest is not None:
        lines.append(f"Open interest: {bubble.open_interest:,.0f}")
    if bubble.implied_volatility is not None:
        lines.append(f"IV: {bubble.implied_volatility:.2%}")
    if bubble.gamma is not None:
        lines.append(f"Gamma: {bubble.gamma:.6f}")
    if bubble.delta is not None:
        lines.append(f"Delta: {bubble.delta:.4f}")
    lines.append(f"Side: {bubble.side.value}")
    if bubble.aggressiveness is not FlowAggressiveness.UNKNOWN:
        lines.append(f"Aggressiveness: {bubble.aggressiveness.value}")
    return "<br>".join(lines)


def _add_flow_bubbles(
    fig: go.Figure,
    bubbles: list[FlowBubble] | None,
    transform: Callable[[float], float],
) -> None:
    if not bubbles:
        return
    specs = (
        (OptionType.CALL, "CALL Flow", COLORS["call_flow"]),
        (OptionType.PUT, "PUT Flow", COLORS["put_flow"]),
    )
    for option_type, name, color in specs:
        side = [bubble for bubble in bubbles if bubble.option_type is option_type]
        if not side:
            continue
        fig.add_trace(go.Scatter(
            x=[bubble.timestamp for bubble in side],
            y=[float(transform(bubble.strike)) for bubble in side],
            mode="markers",
            name=name,
            marker=dict(
                size=[bubble.size for bubble in side],
                color=[_flow_marker_color(bubble) for bubble in side],
                opacity=0.78,
                sizemode="diameter",
                line=dict(color=COLORS["surface"], width=1.4),
            ),
            customdata=_bubble_customdata(side),
            text=[_flow_hover_text(bubble) for bubble in side],
            legendgroup=f"flow-{option_type.value}",
            hovertemplate="%{text}<br>Time: <b>%{x|%H:%M:%S}</b><extra></extra>",
        ))


def merge_relayout_ranges(
    relayout: Mapping | None,
    current_figure: Mapping | None,
) -> dict:
    """Complete partial Plotly relayout events with the other axis range."""
    merged = dict(relayout or {})
    layout = current_figure.get("layout", {}) if isinstance(current_figure, Mapping) else {}
    if not isinstance(layout, Mapping):
        return merged

    for axis in ("xaxis", "yaxis"):
        if merged.get(f"{axis}.autorange") is True:
            continue
        has_range = (
            isinstance(merged.get(f"{axis}.range"), (list, tuple))
            or (f"{axis}.range[0]" in merged and f"{axis}.range[1]" in merged)
        )
        if has_range:
            continue
        axis_layout = layout.get(axis, {})
        previous_range = axis_layout.get("range") if isinstance(axis_layout, Mapping) else None
        if isinstance(previous_range, (list, tuple)) and len(previous_range) == 2:
            merged[f"{axis}.range"] = list(previous_range)
    return merged


def _apply_relayout(fig: go.Figure, relayout: Mapping | None) -> None:
    """Persist an intentional pan/zoom across chart refreshes without snapping back."""
    if not relayout:
        return
    if relayout.get("dragmode") in {"pan", "zoom"}:
        fig.update_layout(dragmode=relayout["dragmode"])
    # Handle an explicit reset per axis without resetting the other axis.
    if relayout.get("autosize"):
        fig.update_layout(autosize=True)
    if relayout.get("xaxis.autorange") is True:
        fig.update_xaxes(autorange=True)
    if relayout.get("yaxis.autorange") is True:
        fig.update_yaxes(autorange=True)

    # Check both formats of relayoutData in Dash:
    # Format A: {"xaxis.range[0]": val0, "xaxis.range[1]": val1}
    # Format B: {"xaxis.range": [val0, val1]}
    x_range = relayout.get("xaxis.range")
    if isinstance(x_range, (list, tuple)) and len(x_range) == 2:
        fig.update_xaxes(range=list(x_range), autorange=False)
    elif relayout.get("xaxis.autorange") is not True:
        x0 = relayout.get("xaxis.range[0]")
        x1 = relayout.get("xaxis.range[1]")
        if x0 is not None and x1 is not None:
            fig.update_xaxes(range=[x0, x1], autorange=False)

    y_range = relayout.get("yaxis.range")
    if isinstance(y_range, (list, tuple)) and len(y_range) == 2:
        try:
            fig.update_yaxes(range=[float(y_range[0]), float(y_range[1])], autorange=False)
        except (ValueError, TypeError):
            pass
    elif relayout.get("yaxis.autorange") is not True:
        y0 = relayout.get("yaxis.range[0]")
        y1 = relayout.get("yaxis.range[1]")
        if y0 is not None and y1 is not None:
            try:
                fig.update_yaxes(range=[float(y0), float(y1)], autorange=False)
            except (ValueError, TypeError):
                pass


def _time_rangebreaks(times: pd.Series) -> list[dict]:
    """Hide only gaps absent from the stored candles, never live data."""
    if len(times) < 2:
        return []
    ordered = pd.Series(pd.to_datetime(times).sort_values().unique())
    gaps = ordered.diff()
    breaks = []
    for idx in gaps[gaps > pd.Timedelta(minutes=5)].index:
        breaks.append({"bounds": [ordered.loc[idx - 1], ordered.loc[idx]]})
    return breaks


def _resample_prices(prices: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    """Aggregate stored bars without inventing OHLC values."""
    rules = {"1m": "1min", "5m": "5min", "15m": "15min", "30m": "30min", "1h": "1h", "4h": "4h"}
    rule = rules.get(timeframe)
    if rule is None:
        return prices
    return (
        prices.set_index("timestamp")
        .resample(rule, origin="start_day")
        .agg({"open": "first", "high": "max", "low": "min", "close": "last"})
        .dropna()
        .reset_index()
    )


def _has_reliable_ohlc(prices: pd.DataFrame) -> bool:
    """Require actual intrabar movement before rendering candlesticks."""
    if len(prices) < 2:
        return False
    numeric = prices[["open", "high", "low", "close"]].apply(pd.to_numeric, errors="coerce")
    if numeric.isna().any().any():
        return False
    valid_bounds = (
        (numeric["high"] >= numeric[["open", "close"]].max(axis=1))
        & (numeric["low"] <= numeric[["open", "close"]].min(axis=1))
        & (numeric["high"] >= numeric["low"])
    )
    return bool(valid_bounds.all() and (numeric["high"] > numeric["low"]).any())


def build_options_overlay(
    symbol: str,
    chain: pd.DataFrame | None,
    spot: float | None,
    gamma_flip: float | None,
    keys: dict | None,
    day: str,
    window: float,
    transform: Callable[[float | np.ndarray], float | np.ndarray] | None = None,
    show_price: bool = True,
    show_call_wall: bool = True,
    show_put_wall: bool = True,
    show_gamma_flip: bool = True,
    show_current_price: bool = True,
    show_flow: bool = True,
    show_annotations: bool = True,
    flow_bubbles: list[FlowBubble] | None = None,
    gex_levels: list[GEXLevel] | None = None,
    price_series: pd.DataFrame | None = None,
    previous_price_series: pd.DataFrame | None = None,
    snapshots: list[tuple[datetime, pd.DataFrame]] | None = None,
    relayout: dict | None = None,
    timeframe: str = "2d",
) -> go.Figure:
    """Build the interactive candle/GEX overlay for the selected session."""
    prices = price_series.copy() if price_series is not None else pd.DataFrame()
    needed = {"timestamp", "open", "high", "low", "close"}
    if prices.empty:
        return _empty(f"No hay velas OHLC reales disponibles para {symbol} en la sesión {day}.")
    if chain is None or chain.empty:
        chain = pd.DataFrame(columns=["strike", "type", "gex", "open_interest", "volume"])
    if not spot or spot <= 0:
        spot = float(prices["close"].iloc[-1])

    # Keep the previous saved session available for a centered multi-session view.
    if timeframe in {"2d", "all"}:
        if previous_price_series is not None:
            prev_prices = previous_price_series.copy()
        else:
            prev_prices = pd.DataFrame()
        if not prev_prices.empty and needed.issubset(prev_prices.columns):
            prev_prices = prev_prices.dropna(subset=list(needed)).copy()
            prev_prices["timestamp"] = pd.to_datetime(prev_prices["timestamp"])
            if not prices.empty and needed.issubset(prices.columns):
                prices["timestamp"] = pd.to_datetime(prices["timestamp"])
                prices = pd.concat([prev_prices.tail(390), prices], ignore_index=True)
            else:
                prices = prev_prices

    if prices.empty or not needed.issubset(prices.columns):
        return _empty(f"No hay velas OHLC reales disponibles para {symbol} en la sesión {day}.")

    prices = prices.dropna(subset=list(needed)).copy()
    if prices.empty:
        return _empty(f"No hay velas OHLC válidas disponibles para {symbol} en la sesión {day}.")
    prices["timestamp"] = pd.to_datetime(prices["timestamp"])
    prices = prices.sort_values("timestamp").drop_duplicates("timestamp", keep="last")
    timeframe_limits = {"1h": pd.Timedelta(hours=1), "4h": pd.Timedelta(hours=4),
                        "1d": pd.Timedelta(days=1), "2d": pd.Timedelta(days=2)}
    if timeframe in timeframe_limits:
        cutoff = prices["timestamp"].max() - timeframe_limits[timeframe]
        prices = prices[prices["timestamp"] >= cutoff]
    prices = _resample_prices(prices, timeframe)
    if prices.empty:
        return _empty(f"No hay velas disponibles para la temporalidad {timeframe}.")
    transform = transform or (lambda value: value)

    def tx(value):
        return transform(value)

    times = prices["timestamp"]
    fig = go.Figure()

    reliable_ohlc = _has_reliable_ohlc(prices)
    if show_price and reliable_ohlc:
        o_tx = tx(prices["open"].to_numpy())
        h_tx = tx(prices["high"].to_numpy())
        l_tx = tx(prices["low"].to_numpy())
        c_tx = tx(prices["close"].to_numpy())
        fig.add_trace(go.Candlestick(
            x=times, open=o_tx, high=h_tx, low=l_tx, close=c_tx,
            name="Price",
            whiskerwidth=0.7,
            increasing_line_color=COLORS["up"],
            decreasing_line_color=COLORS["down"],
            increasing_fillcolor=COLORS["up"],
            decreasing_fillcolor=COLORS["down"],
            increasing_line_width=1.8,
            decreasing_line_width=1.8,
            hovertemplate=(
                "<b>%{x|%Y-%m-%d %H:%M}</b><br>"
                "Open: %{open:,.2f}<br>"
                "High: %{high:,.2f}<br>"
                "Low: %{low:,.2f}<br>"
                "Close: %{close:,.2f}<extra></extra>"
            ),
        ))
    elif show_price:
        fig.add_trace(go.Scatter(
            x=times,
            y=tx(prices["close"].to_numpy()),
            mode="lines",
            name="Spot",
            line=dict(color=COLORS["spot"], width=2),
            hovertemplate=(
                "<b>%{x|%Y-%m-%d %H:%M}</b><br>"
                "Spot: %{y:,.2f}<extra></extra>"
            ),
        ))

    keys = keys or {}
    prepared_levels = gex_levels if gex_levels is not None else _legacy_gex_levels(
        chain,
        float(spot),
        gamma_flip,
        keys,
        show_call_wall,
        show_put_wall,
        show_gamma_flip,
    )
    resolved_levels = [
        level for level in prepared_levels
        if _level_enabled(level, show_call_wall, show_put_wall, show_gamma_flip)
    ]

    # Determine largest GEX magnitude to scale wall vivacity and thickness
    largest_gex = max((abs(level.value or 0.0) for level in resolved_levels), default=0.0) or 1.0

    annotations = []
    for level in resolved_levels:
        raw_value = level.price
        label = level.name
        color = COLORS.get(level.color_key or "flip", COLORS["flip"])
        glow_color = COLORS.get(level.glow_key or "flip_glow", COLORS["flip_glow"])
        gex = float(level.value or 0.0)
        oi = float(level.open_interest or 0.0)
        volume = float(level.volume or 0.0)
        dash = level.style
        rel_strength = min(1.0, max(0.15, abs(gex) / largest_gex if largest_gex else 0.5))
        dist_pct = ((raw_value - spot) / spot) * 100.0 if spot else 0.0
        dist_str = f"{dist_pct:+.2f}%"
        gex_badge = _fmt_gex(gex)
        strength_pct = int(rel_strength * 100)

        # 1. Halo / Glow trace behind wall (gives vivid visual presence of wall size)
        halo_width = float(2.5 + 2.5 * np.sqrt(rel_strength))
        fig.add_trace(go.Scatter(
            x=times, y=np.repeat(float(tx(raw_value)), len(times)),
            mode="lines", showlegend=False,
            line=dict(color=glow_color, width=halo_width),
            opacity=0.55,
            hoverinfo="skip",
        ))

        # 2. Main Wall Line with interactive hover card
        line_width = float(1.25 + 1.25 * np.sqrt(rel_strength))
        custom = np.repeat([[gex, oi, volume]], len(times), axis=0)

        fig.add_trace(go.Scatter(
            x=times, y=np.repeat(float(tx(raw_value)), len(times)),
            mode="lines", name=label,
            line=dict(color=color, width=line_width, dash=dash),
            customdata=custom,
            hovertemplate=(
                f"<b style='color:{color}'>━━ {label} ━━</b><br>"
                "Strike: <b>%{y:,.2f}</b> (" + dist_str + " vs Spot)<br>"
                "GEX: %{customdata[0]:+,.0f}<br>"
                f"Fuerza Muro: <b>{strength_pct}%</b><br>"
                "Open interest: %{customdata[1]:,.0f}<br>"
                "Volume: %{customdata[2]:,.0f}<extra></extra>"
            ),
        ))

        # Keep the plot readable when several adjacent walls are present. All
        # lines remain interactive and visible in the legend; only the primary
        # level of each family gets a persistent badge.
        primary_badge = label in {"Call Wall", "Put Wall", "Gamma Flip"}
        if primary_badge:
            annotations.append(dict(
                xref="paper", yref="y",
                x=1.005, y=float(tx(raw_value)),
                text=f"<b>{label}</b>: {float(tx(raw_value)):,.1f} ({gex_badge})",
                showarrow=False,
                font=dict(color=COLORS["surface"], size=10, family="Inter, monospace"),
                align="left",
                bgcolor=color,
                bordercolor=COLORS["grid"],
                borderwidth=1,
                borderpad=3,
                opacity=0.94,
            ))

    activity_window = min(max(window, 0.015), 0.04)
    _add_gamma_activity(fig, _gamma_activity_points(snapshots, spot, activity_window), tx)
    if show_flow:
        _add_flow_bubbles(fig, flow_bubbles, tx)
    log.info("Rendering options-flow overlay with %s flow bubbles", len(flow_bubbles or []))

    shown_spot = float(tx(float(spot)))
    if show_current_price:
        spot_custom = np.repeat([[0.0, 0.0, 0.0, 0, "0.00%"]], len(times), axis=0)
        fig.add_trace(go.Scatter(
            x=times, y=np.repeat(shown_spot, len(times)),
            mode="lines", name="Current price",
            line=dict(color=COLORS["spot"], width=1.5, dash="dot"),
            customdata=spot_custom,
            hovertemplate=(
                f"<b style='color:{COLORS['spot']}'>● Current price (Spot)</b><br>"
                "Price: <b>%{y:,.2f}</b><extra></extra>"
            ),
        ))

        # Spot right-side badge
        annotations.append(dict(
            xref="paper", yref="y",
            x=1.005, y=shown_spot,
            text=f"<b>Spot</b>: {shown_spot:,.1f}",
            showarrow=False,
            font=dict(color=COLORS["surface"], size=10, family="Inter, monospace"),
            align="left",
            bgcolor=COLORS["spot"],
            bordercolor=COLORS["grid"],
            borderwidth=1,
            borderpad=3,
            opacity=0.95,
        ))

    focus_window = min(max(window, 0.012), 0.025)
    level_values = [level.price for level in resolved_levels]
    range_low = min([spot * (1 - focus_window), *level_values])
    range_high = max([spot * (1 + focus_window), *level_values])
    if range_high <= range_low:
        range_low, range_high = spot * 0.98, spot * 1.02
    padding = max((range_high - range_low) * 0.06, spot * 0.001)

    fig.update_layout(
        title=dict(
            text=f"<b>{symbol}</b> · Live price + GEX levels · {day}",
            x=0.01, xanchor="left",
            font=dict(color=COLORS["ink"], size=15, family="Inter, sans-serif"),
        ),
        height=620,
        paper_bgcolor=COLORS["surface"],
        plot_bgcolor=COLORS["surface"],
        margin=dict(l=64, r=130, t=56, b=48),
        font=dict(color=COLORS["muted"], family="Inter, sans-serif"),
        hovermode="closest",
        dragmode="pan",
        hoverlabel=dict(
            bgcolor="rgba(11, 15, 25, 0.95)",
            bordercolor=COLORS["grid"],
            font=dict(color=COLORS["ink"], family="Inter, monospace", size=12),
        ),
        legend=dict(
            orientation="h", y=1.09, x=0,
            font=dict(color=COLORS["muted"], size=11),
            bgcolor="rgba(0,0,0,0)",
        ),
        xaxis=dict(
            title="Time",
            gridcolor=COLORS["grid"],
            zeroline=False,
            fixedrange=False,
            rangeslider=dict(visible=False),
            range=[times.iloc[0], times.iloc[-1]],
            autorange=False,
            rangebreaks=_time_rangebreaks(times),
        ),
        yaxis=dict(
            title="Price / strike",
            gridcolor=COLORS["grid"],
            zeroline=False,
            fixedrange=False,
            range=sorted(tx(np.asarray([range_low - padding, range_high + padding]))),
            autorange=False,
            side="left",
        ),
        annotations=annotations if show_annotations else [],
    )
    _apply_relayout(fig, relayout)
    
    # Aplicar animación de entrada para options overlay
    fig = animation_engine.apply_entry_animation(fig, chart_type="line")
    
    return fig


def build_options_overlay_from_view_model(
    view_model: OptionsOverlayViewModel,
    transform: Callable[[float | np.ndarray], float | np.ndarray] | None = None,
    show_price: bool = True,
    show_call_wall: bool = True,
    show_put_wall: bool = True,
    show_gamma_flip: bool = True,
    show_current_price: bool = True,
    show_flow: bool = True,
    show_annotations: bool = True,
    relayout: dict | None = None,
    timeframe: str = "2d",
) -> go.Figure:
    """Render an overlay from an application-prepared view model."""
    return build_options_overlay(
        view_model.symbol,
        view_model.chain,
        view_model.current_price,
        view_model.gamma_flip,
        view_model.keys,
        view_model.day,
        view_model.window,
        transform=transform,
        show_price=show_price,
        show_call_wall=show_call_wall,
        show_put_wall=show_put_wall,
        show_gamma_flip=show_gamma_flip,
        show_current_price=show_current_price,
        show_flow=show_flow,
        show_annotations=show_annotations,
        flow_bubbles=view_model.flow_bubbles,
        gex_levels=view_model.gex_levels or None,
        price_series=view_model.price_series,
        previous_price_series=view_model.previous_price_series,
        snapshots=view_model.snapshots,
        relayout=relayout,
        timeframe=timeframe,
    )
