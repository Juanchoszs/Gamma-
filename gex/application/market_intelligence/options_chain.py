"""Options-chain view model built from an already enriched chain.

The service deliberately aggregates existing option metrics. It does not fetch
quotes or recompute Greeks/GEX, keeping quantitative ownership in the backend
pipeline that produced the chain.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

import numpy as np
import pandas as pd

from gex.domain.market.intelligence import LevelType, MarketLevel


@dataclass(frozen=True)
class OptionsChainConfig:
    expiration: str | None = None
    strike_range_pct: float = 5.0
    side: str = "ALL"
    min_volume: float = 0.0
    min_open_interest: float = 0.0
    min_abs_net_gex: float = 0.0
    min_abs_delta: float = 0.0
    max_rows: int = 100

    def __post_init__(self) -> None:
        if self.strike_range_pct < 0:
            raise ValueError("strike_range_pct must be non-negative")
        if self.max_rows <= 0:
            raise ValueError("max_rows must be positive")
        if self.side.upper() not in {"ALL", "CALLS", "PUTS"}:
            raise ValueError("side must be ALL, CALLS, or PUTS")
        if any(value < 0 for value in (
            self.min_volume,
            self.min_open_interest,
            self.min_abs_net_gex,
            self.min_abs_delta,
        )):
            raise ValueError("options-chain thresholds must be non-negative")


def available_expirations(chain: pd.DataFrame | None) -> list[str]:
    """Return normalized sorted expirations available in an enriched chain."""
    if chain is None or chain.empty or "expiry" not in chain:
        return []
    values = pd.to_datetime(chain["expiry"], errors="coerce").dropna()
    return sorted({value.date().isoformat() for value in values})


def build_options_chain_payload(
    *,
    chain: pd.DataFrame | None,
    spot: float,
    levels: Iterable[MarketLevel] = (),
    config: OptionsChainConfig | None = None,
) -> dict[str, Any]:
    """Produce strike rows plus deterministic highlights for the options UI."""
    if spot <= 0:
        raise ValueError("spot must be positive")
    cfg = config or OptionsChainConfig()
    original = chain if chain is not None else pd.DataFrame()
    expirations = available_expirations(original)
    rows = _filtered_rows(original, spot, cfg)
    highlighted = _highlighted_strikes(rows, spot, levels)
    output = _strike_rows(rows, spot, cfg, highlighted)
    return {
        "spot": float(spot),
        "expiration": cfg.expiration,
        "side": cfg.side.upper(),
        "strike_range_pct": cfg.strike_range_pct,
        "filters": {
            "min_volume": cfg.min_volume,
            "min_open_interest": cfg.min_open_interest,
            "min_abs_net_gex": cfg.min_abs_net_gex,
            "min_abs_delta": cfg.min_abs_delta,
        },
        "available_expirations": expirations,
        "rows": output,
        "row_count": len(output),
    }


def _filtered_rows(chain: pd.DataFrame, spot: float, cfg: OptionsChainConfig) -> pd.DataFrame:
    required = {"strike", "type"}
    if chain.empty or not required.issubset(chain.columns):
        return pd.DataFrame(columns=["strike", "type"])
    rows = chain.copy()
    rows["strike"] = pd.to_numeric(rows["strike"], errors="coerce")
    rows = rows[rows["strike"].notna()]
    rows["type"] = rows["type"].astype(str).str.upper().str[0]
    rows = rows[rows["type"].isin(["C", "P"])]
    if cfg.expiration and "expiry" in rows:
        expiry = pd.to_datetime(rows["expiry"], errors="coerce").dt.date.astype(str)
        rows = rows[expiry == cfg.expiration]
    if cfg.side.upper() == "CALLS":
        rows = rows[rows["type"] == "C"]
    elif cfg.side.upper() == "PUTS":
        rows = rows[rows["type"] == "P"]
    lower = spot * (1.0 - cfg.strike_range_pct / 100.0)
    upper = spot * (1.0 + cfg.strike_range_pct / 100.0)
    return rows[rows["strike"].between(lower, upper)]


def _highlighted_strikes(
    rows: pd.DataFrame,
    spot: float,
    levels: Iterable[MarketLevel],
) -> dict[float, list[str]]:
    if rows.empty:
        return {}
    strikes = sorted(float(value) for value in rows["strike"].unique())
    highlights: dict[float, list[str]] = {min(strikes, key=lambda value: abs(value - spot)): ["ATM"]}
    by_type = {
        LevelType.CALL_WALL: "CALL WALL",
        LevelType.PUT_WALL: "PUT WALL",
        LevelType.GAMMA_FLIP: "GAMMA FLIP",
        LevelType.GEX_WALL: "GEX WALL",
        LevelType.OI_NODE: "OI NODE",
        LevelType.VOLUME_NODE: "VOLUME NODE",
    }
    for level in levels:
        label = by_type.get(level.level_type)
        if label is None:
            continue
        strike = _nearest_strike(strikes, level.price)
        if strike is not None and np.isclose(strike, level.price, rtol=0.0, atol=_strike_tolerance(strikes)):
            highlights.setdefault(strike, []).append(label)
    grouped = rows.groupby("strike", sort=True)
    for column, label in (("open_interest", "HIGH OI"), ("volume", "HIGH VOLUME")):
        if column not in rows:
            continue
        totals = grouped[column].sum()
        if not totals.empty and float(totals.max()) > 0:
            highlights.setdefault(float(totals.idxmax()), []).append(label)
    net_gex = grouped["gex"].sum() if "gex" in rows else pd.Series(dtype=float)
    if not net_gex.empty and float(net_gex.abs().max()) > 0:
        highlights.setdefault(float(net_gex.abs().idxmax()), []).append("LARGE GEX")
    iv_column = "iv" if "iv" in rows else None
    if iv_column:
        average_iv = grouped[iv_column].mean()
        if not average_iv.empty and float(average_iv.max()) > 0:
            highlights.setdefault(float(average_iv.idxmax()), []).append("HIGH IV")
    return {strike: list(dict.fromkeys(labels)) for strike, labels in highlights.items()}


def _strike_rows(
    rows: pd.DataFrame,
    spot: float,
    cfg: OptionsChainConfig,
    highlights: dict[float, list[str]],
) -> list[dict[str, Any]]:
    if rows.empty:
        return []
    output: list[dict[str, Any]] = []
    for strike, strike_rows in rows.groupby("strike", sort=True):
        call = _metrics(strike_rows[strike_rows["type"] == "C"])
        put = _metrics(strike_rows[strike_rows["type"] == "P"])
        output.append({
            "strike": float(strike),
            "distance_percent": ((float(strike) - spot) / spot) * 100.0,
            "call": call,
            "put": put,
            "net_gex": float(call["gex"] + put["gex"]),
            "flags": highlights.get(float(strike), []),
        })
    output = [row for row in output if _matches_metric_thresholds(row, cfg)]
    closest = sorted(output, key=lambda row: (abs(row["strike"] - spot), row["strike"]))
    selected = closest[:cfg.max_rows]
    return sorted(selected, key=lambda row: row["strike"])


def _metrics(rows: pd.DataFrame) -> dict[str, float]:
    if rows.empty:
        return {"open_interest": 0.0, "volume": 0.0, "gex": 0.0, "iv": 0.0, "delta": 0.0}
    return {
        "open_interest": _sum(rows, "open_interest"),
        "volume": _sum(rows, "volume"),
        "gex": _sum(rows, "gex"),
        "iv": _mean(rows, "iv"),
        "delta": _mean(rows, "delta_bs", fallback="delta"),
    }


def _matches_metric_thresholds(row: dict[str, Any], cfg: OptionsChainConfig) -> bool:
    """Filter aggregated strike rows, keeping calls and puts in one context."""
    call = row["call"]
    put = row["put"]
    volume = call["volume"] + put["volume"]
    open_interest = call["open_interest"] + put["open_interest"]
    max_abs_delta = max(abs(call["delta"]), abs(put["delta"]))
    return (
        volume >= cfg.min_volume
        and open_interest >= cfg.min_open_interest
        and abs(row["net_gex"]) >= cfg.min_abs_net_gex
        and max_abs_delta >= cfg.min_abs_delta
    )


def _sum(rows: pd.DataFrame, column: str) -> float:
    if column not in rows:
        return 0.0
    return float(pd.to_numeric(rows[column], errors="coerce").fillna(0.0).sum())


def _mean(rows: pd.DataFrame, column: str, *, fallback: str | None = None) -> float:
    active = column if column in rows else fallback
    if active is None or active not in rows:
        return 0.0
    values = pd.to_numeric(rows[active], errors="coerce").dropna()
    return float(values.mean()) if not values.empty else 0.0


def _nearest_strike(strikes: list[float], price: float) -> float | None:
    return min(strikes, key=lambda strike: abs(strike - price)) if strikes else None


def _strike_tolerance(strikes: list[float]) -> float:
    if len(strikes) < 2:
        return 0.01
    steps = [right - left for left, right in zip(strikes, strikes[1:]) if right > left]
    return max(min(steps, default=0.01) / 2.0, 0.01)
