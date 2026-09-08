"""Vista intradía de liquidez: una lectura principal, sin datos inventados."""
from __future__ import annotations

from datetime import datetime
import time

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from gex.adapters.persistence import store
from gex.domain.gex import metrics
from gex.domain.gex.metrics import ET
from gex.presentation.i18n.i18n import t


COLORS = {
    "page": "#090d16", "surface": "#101827", "grid": "#243044",
    "muted": "#94a3b8", "ink": "#e5edf8", "spot": "#f8fafc",
    "flip": "#fbbf24", "call": "#22d3ee", "put": "#fb7185",
}
_SNAPSHOT_CACHE: dict[
    tuple[str, str], tuple[float, list[tuple[datetime, pd.DataFrame]], float]
] = {}
_SNAPSHOT_CACHE_TTL_S = 5.0


def _price_series(symbol: str, day: str, times: list[pd.Timestamp]) -> np.ndarray | None:
    """Align real stored closes to snapshot times for the white spot line."""
    prices = store.load_prices(symbol, day)
    if prices.empty and symbol in {"ES", "NQ"}:
        prices = store.load_prices({"ES": "SPX", "NQ": "NDX"}[symbol], day)
    required = {"timestamp", "close"}
    if prices.empty or not required.issubset(prices.columns):
        return None
    prices = prices[["timestamp", "close"]].copy()
    prices["timestamp"] = pd.to_datetime(prices["timestamp"])
    prices["close"] = pd.to_numeric(prices["close"], errors="coerce")
    prices = prices.dropna().sort_values("timestamp").drop_duplicates("timestamp", keep="last")
    if prices.empty:
        return None
    source = prices.set_index("timestamp")["close"]
    aligned = source.reindex(pd.DatetimeIndex(times), method="nearest")
    return aligned.to_numpy(dtype=float)


def _empty(message: str) -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(text=message, showarrow=False, font=dict(color=COLORS["muted"], size=14))
    fig.update_layout(
        height=560, paper_bgcolor=COLORS["surface"], plot_bgcolor=COLORS["surface"],
        margin=dict(l=48, r=28, t=44, b=42), xaxis=dict(visible=False), yaxis=dict(visible=False),
    )
    return fig


def _snapshots(symbol: str, day: str) -> tuple[list[tuple[datetime, pd.DataFrame]], float]:
    cache_key = (symbol, day)
    cached = _SNAPSHOT_CACHE.get(cache_key)
    now = time.monotonic()
    if cached and now - cached[0] < _SNAPSHOT_CACHE_TTL_S:
        return cached[1], cached[2]

    columns = [
        "strike", "spot", "gex", "open_interest", "volume", "expiry",
        "iv", "t_years", "type",
    ]
    snapshots = store.load_day_snapshots(symbol, day, columns=columns)
    if len(snapshots) < 2 and symbol in {"NQ", "ES"}:
        fallback = "NDX" if symbol == "NQ" else "SPX"
        alternate = store.load_day_snapshots(fallback, day, columns=columns)
        if len(alternate) > len(snapshots):
            snapshots = alternate
    if not snapshots:
        return [], 0.0
    latest = snapshots[-1][1]
    spot = float(latest["spot"].iloc[0]) if "spot" in latest and not latest.empty else 0.0
    _SNAPSHOT_CACHE[cache_key] = (now, snapshots, spot)
    return snapshots, spot


def _metric(frame: pd.DataFrame, metric: str, spot: float) -> pd.Series:
    if metric == "oi":
        return frame.groupby("strike")["open_interest"].sum()
    if metric == "vol":
        return frame.groupby("strike")["volume"].sum()
    if "gex" in frame.columns:
        return frame.groupby("strike")["gex"].sum().abs() / 1e6
    return metrics.gex_by_strike_weighted(frame, spot, "open_interest").abs() / 1e6


def build_intraday_heatmap(
    symbol: str, lang: str, day: str, window: float, xf=None, unit: str | None = None,
    levels_shown: list[str] | None = None, metric: str = "gex",
    relayout: dict | None = None,
) -> go.Figure:
    """Renderiza una matriz strike × tiempo con spot y niveles reales.

    No sintetiza velas. La línea de precio solo se dibuja a partir del spot
    registrado con cada snapshot, que es la única señal disponible siempre.
    """
    transform = xf or (lambda value: value)
    levels_shown = levels_shown or ["zero_gamma", "call_wall", "put_support"]
    snapshots, spot = _snapshots(symbol, day)
    if not snapshots or spot <= 0:
        return _empty(t(lang, "heat_none", day=day))

    effective_window = max(window, 0.10 if spot > 10_000 else window)
    if spot > 40_000:
        effective_window = max(window, 0.20)
    low, high = spot * (1 - effective_window), spot * (1 + effective_window)

    by_minute: dict[pd.Timestamp, tuple[pd.DataFrame, float]] = {}
    for timestamp, frame in snapshots:
        if frame.empty or "strike" not in frame:
            continue
        key = pd.Timestamp(timestamp).floor("min")
        snapshot_spot = float(frame["spot"].iloc[0]) if "spot" in frame else spot
        by_minute[key] = (frame, snapshot_spot)
    if not by_minute:
        return _empty(t(lang, "heat_none", day=day))

    times = sorted(by_minute)
    latest = by_minute[times[-1]][0]
    latest = latest[latest["strike"].between(low, high)]
    if latest.empty:
        return _empty(t(lang, "no_data_window"))

    strikes = np.sort(latest["strike"].dropna().unique())
    matrix = np.zeros((len(strikes), len(times)), dtype=float)
    spots: list[float] = []

    for column, timestamp in enumerate(times):
        frame, snapshot_spot = by_minute[timestamp]
        selected = frame[frame["strike"].isin(strikes)]
        values = _metric(selected, metric, snapshot_spot)
        if not values.empty:
            # Reindex once per snapshot instead of assigning cell by cell.
            # This keeps large option chains in vectorized pandas/numpy code.
            matrix[:, column] = values.reindex(strikes, fill_value=0.0).to_numpy(dtype=float)
        spots.append(snapshot_spot)

    max_value = float(matrix.max()) if matrix.size else 0.0
    normalized = matrix / max_value * 100 if max_value > 0 else matrix
    y_values = transform(strikes)
    metric_label = {"gex": "GEX concentration ($M)", "oi": "Open interest", "vol": "Volume"}.get(metric, "Exposure")

    fig = go.Figure()
    fig.add_trace(go.Heatmap(
        x=times, y=y_values, z=normalized,
        colorscale=[
            [0.0, "#101827"], [0.15, "#172554"], [0.42, "#155e75"],
            [0.68, "#0891b2"], [0.86, "#22c55e"], [1.0, "#fbbf24"],
        ],
        zmin=0, zmax=100, colorbar=dict(title="Intensity", thickness=12, tickfont=dict(color=COLORS["muted"])),
        hovertemplate=("<b>Strike</b> %{y:,.0f}<br><b>Time</b> %{x|%H:%M}<br>"
                       f"<b>{metric_label}</b> %{{z:.1f}}%<extra></extra>"),
        name=metric_label,
    ))
    real_prices = _price_series(symbol, day, times)
    display_spots = real_prices if real_prices is not None else np.asarray(spots)
    fig.add_trace(go.Scatter(
        x=times, y=transform(display_spots), mode="lines", name=t(lang, "legend_spot"),
        line=dict(color="#ffffff", width=2.4), hovertemplate=f"<b>{t(lang, 'legend_spot')}</b> %{{y:,.2f}}<br>%{{x|%H:%M}}<extra></extra>",
    ))

    levels = metrics.key_levels(latest, spot, ref_spot=spot, all_expiries=True)
    level_specs = [("zero_gamma", metrics.zero_gamma(latest, spot), "Gamma Flip", COLORS["flip"]),
                   ("call_wall", levels.get("call_wall"), "Call Wall", COLORS["call"]),
                   ("put_support", levels.get("put_support"), "Put Support", COLORS["put"])]
    transformed_low, transformed_high = sorted(transform(np.asarray([low, high])))
    for key, value, label, color in level_specs:
        if key in levels_shown and value is not None:
            y_value = float(transform(value))
            if transformed_low <= y_value <= transformed_high:
                fig.add_hline(y=y_value, line_color=color, line_width=1.3, line_dash="dot",
                              annotation_text=label, annotation_font_color=color,
                              annotation_position="top right")

    fig.update_layout(
        title=dict(text=f"{symbol} · Intraday market structure", x=0.01, xanchor="left", font=dict(color=COLORS["ink"], size=15)),
        height=620, paper_bgcolor=COLORS["surface"], plot_bgcolor=COLORS["surface"],
        margin=dict(l=62, r=52, t=54, b=48), font=dict(color=COLORS["muted"], family="Inter, sans-serif"),
        hoverlabel=dict(bgcolor=COLORS["page"], font=dict(color=COLORS["ink"])),
        legend=dict(orientation="h", y=1.07, x=0, font=dict(color=COLORS["muted"])),
        uirevision=f"heat-{symbol}-{day}-{unit}-{window}-{metric}",
        xaxis=dict(title=t(lang, "heat_axis_time"), gridcolor=COLORS["grid"], tickformat="%H:%M"),
        yaxis=dict(title=t(lang, "heat_axis_strike"), gridcolor=COLORS["grid"], fixedrange=False),
    )
    if relayout:
        x_range = relayout.get("xaxis.range")
        y_range = relayout.get("yaxis.range")
        if not isinstance(x_range, (list, tuple)):
            x_range = [relayout.get("xaxis.range[0]"), relayout.get("xaxis.range[1]")]
        if not isinstance(y_range, (list, tuple)):
            y_range = [relayout.get("yaxis.range[0]"), relayout.get("yaxis.range[1]")]
        if len(x_range) == 2 and all(value is not None for value in x_range):
            fig.update_xaxes(range=list(x_range), autorange=False)
        if len(y_range) == 2 and all(value is not None for value in y_range):
            fig.update_yaxes(range=[float(value) for value in y_range], autorange=False)
    return fig
