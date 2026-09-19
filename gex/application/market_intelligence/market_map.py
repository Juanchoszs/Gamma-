"""Market map payloads combining price, positioning and structure."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable

import pandas as pd

from gex.application.market_intelligence.dto import market_level_to_dict, market_state_to_dict
from gex.domain.market.intelligence import MarketLevel, MarketState


@dataclass(frozen=True)
class MarketMapConfig:
    strike_window_pct: float | None = 3.0
    max_rows: int = 120

    def __post_init__(self) -> None:
        if self.strike_window_pct is not None and self.strike_window_pct < 0:
            raise ValueError("strike_window_pct must be non-negative")
        if self.max_rows <= 0:
            raise ValueError("max_rows must be positive")


def build_market_map_payload(
    *,
    symbol: str,
    timestamp: datetime,
    spot: float,
    chain: pd.DataFrame | None,
    levels: Iterable[MarketLevel],
    state: MarketState | None = None,
    config: MarketMapConfig | None = None,
) -> dict[str, Any]:
    """Build API-ready market map data without chart-library dependencies."""
    if spot <= 0:
        raise ValueError("spot must be positive")
    cfg = config or MarketMapConfig()
    frame = chain if chain is not None else pd.DataFrame()
    rows = _exposure_rows(frame, spot=spot, config=cfg)
    payload: dict[str, Any] = {
        "symbol": symbol,
        "timestamp": timestamp.isoformat(),
        "spot": float(spot),
        "exposure_axis": "strike",
        "positioning_axis": "net_gex",
        "rows": rows,
        "levels": [market_level_to_dict(level) for level in levels],
    }
    if state is not None:
        payload["state"] = market_state_to_dict(state)
    return payload


def _exposure_rows(
    frame: pd.DataFrame,
    *,
    spot: float,
    config: MarketMapConfig,
) -> list[dict[str, Any]]:
    required = {"strike", "type"}
    if frame.empty or not required.issubset(frame.columns):
        return []
    rows = frame.copy()
    rows = rows[rows["strike"].notna()]
    rows["strike"] = rows["strike"].astype(float)
    if config.strike_window_pct is not None:
        lower = spot * (1.0 - config.strike_window_pct / 100.0)
        upper = spot * (1.0 + config.strike_window_pct / 100.0)
        rows = rows[(rows["strike"] >= lower) & (rows["strike"] <= upper)]
    if rows.empty:
        return []

    grouped: list[dict[str, Any]] = []
    for strike, strike_rows in rows.groupby("strike", sort=True):
        calls = strike_rows[strike_rows["type"] == "C"]
        puts = strike_rows[strike_rows["type"] == "P"]
        call_gex = _sum(calls, "gex")
        put_gex = _sum(puts, "gex")
        grouped.append({
            "strike": float(strike),
            "distance_percent": ((float(strike) - spot) / spot) * 100.0,
            "call_gex": call_gex,
            "put_gex": put_gex,
            "net_gex": call_gex + put_gex,
            "call_open_interest": _sum(calls, "open_interest"),
            "put_open_interest": _sum(puts, "open_interest"),
            "call_volume": _sum(calls, "volume"),
            "put_volume": _sum(puts, "volume"),
            "expiration_count": int(strike_rows["expiry"].nunique()) if "expiry" in strike_rows else 0,
        })
    ranked = sorted(grouped, key=lambda row: (abs(row["strike"] - spot), -abs(row["net_gex"])))
    return sorted(ranked[:config.max_rows], key=lambda row: row["strike"])


def _sum(frame: pd.DataFrame, column: str) -> float:
    if frame.empty or column not in frame:
        return 0.0
    return float(frame[column].fillna(0.0).sum())
