"""Build unified market-intelligence levels from existing GEX outputs."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import numpy as np
import pandas as pd

from gex.domain.market.intelligence import (
    LevelSource,
    LevelType,
    MarketLevel,
    SessionType,
)


@dataclass(frozen=True)
class LevelBuildConfig:
    max_gex_levels: int = 3
    include_volume_nodes: bool = True
    include_oi_nodes: bool = True
    min_wall_strength: int = 0

    def __post_init__(self) -> None:
        if self.max_gex_levels < 0:
            raise ValueError("max_gex_levels must be non-negative")
        if not 0 <= self.min_wall_strength <= 100:
            raise ValueError("min_wall_strength must be between 0 and 100")


def build_market_levels_from_gex_outputs(
    *,
    chain: pd.DataFrame | None,
    timestamp: datetime,
    keys: dict | None,
    zero_gamma: float | None = None,
    session: SessionType = SessionType.UNKNOWN,
    config: LevelBuildConfig | None = None,
) -> tuple[MarketLevel, ...]:
    """Normalize existing GEX outputs into the unified MarketLevel contract."""
    cfg = config or LevelBuildConfig()
    frame = chain if chain is not None else pd.DataFrame()
    keys = keys or {}
    maxes = _metric_maxes(frame)
    levels: list[MarketLevel] = []

    for price in _key_prices(keys, "call_walls", "call_wall"):
        level = _level(frame, timestamp, LevelType.CALL_WALL, price, "C", maxes, session)
        if level.strength >= cfg.min_wall_strength:
            levels.append(level)
    for price in _key_prices(keys, "put_supports", "put_support"):
        level = _level(frame, timestamp, LevelType.PUT_WALL, price, "P", maxes, session)
        if level.strength >= cfg.min_wall_strength:
            levels.append(level)
    if zero_gamma is not None:
        levels.append(_level(frame, timestamp, LevelType.GAMMA_FLIP, float(zero_gamma), None, maxes, session))

    high_gamma_price = _extreme_gex_price(frame, positive=True)
    if high_gamma_price is not None:
        levels.append(_level(frame, timestamp, LevelType.HIGH_GAMMA, high_gamma_price, None, maxes, session))
    low_gamma_price = _extreme_gex_price(frame, positive=False)
    if low_gamma_price is not None:
        levels.append(_level(frame, timestamp, LevelType.LOW_GAMMA, low_gamma_price, None, maxes, session))

    for price in _top_gex_prices(frame, cfg.max_gex_levels):
        levels.append(_level(frame, timestamp, LevelType.GEX_WALL, price, None, maxes, session))

    if cfg.include_volume_nodes:
        volume_price = _top_metric_price(frame, "volume")
        if volume_price is not None:
            levels.append(_level(frame, timestamp, LevelType.VOLUME_NODE, volume_price, None, maxes, session))
    if cfg.include_oi_nodes:
        oi_price = _top_metric_price(frame, "open_interest")
        if oi_price is not None:
            levels.append(_level(frame, timestamp, LevelType.OI_NODE, oi_price, None, maxes, session))

    return _dedupe_levels(levels)


def _key_prices(keys: dict, plural_key: str, singular_key: str) -> tuple[float, ...]:
    explicit = keys.get(plural_key)
    if isinstance(explicit, (list, tuple)):
        return tuple(float(value) for value in explicit if value is not None)
    value = keys.get(singular_key)
    if value is None:
        return ()
    return (float(value),)


def _level(
    frame: pd.DataFrame,
    timestamp: datetime,
    level_type: LevelType,
    price: float,
    side: str | None,
    maxes: dict[str, float],
    session: SessionType,
) -> MarketLevel:
    stats = _level_stats(frame, price, side)
    strength = _strength(stats, maxes)
    level_rows = _level_rows(frame, price, side)
    return MarketLevel(
        id=f"{level_type.value}-{price:g}",
        level_type=level_type,
        price=float(price),
        source=_source_for(level_type),
        timestamp=timestamp,
        strength=strength,
        volume=stats["volume"],
        open_interest=stats["open_interest"],
        gamma=stats["gex"],
        delta=stats["dex"],
        vanna=stats["vex"],
        charm=stats["cex"],
        expiration=_single_expiration(level_rows),
        session=session,
        metadata=_level_metadata(level_rows, side),
    )


def _source_for(level_type: LevelType) -> LevelSource:
    if level_type in {LevelType.VOLUME_NODE, LevelType.OI_NODE}:
        return LevelSource.OPTIONS_CHAIN
    return LevelSource.GEX_ENGINE


def _level_stats(frame: pd.DataFrame, price: float, side: str | None) -> dict[str, float]:
    empty = {"gex": 0.0, "open_interest": 0.0, "volume": 0.0,
             "dex": 0.0, "vex": 0.0, "cex": 0.0}
    rows = _level_rows(frame, price, side)
    if rows.empty:
        return empty
    return {
        "gex": _sum_column(rows, "gex"),
        "open_interest": _sum_column(rows, "open_interest"),
        "volume": _sum_column(rows, "volume"),
        "dex": _sum_column(rows, "dex"),
        "vex": _sum_column(rows, "vex"),
        "cex": _sum_column(rows, "cex"),
    }


def _level_rows(frame: pd.DataFrame, price: float, side: str | None) -> pd.DataFrame:
    if frame.empty or "strike" not in frame.columns:
        return pd.DataFrame()
    strike = pd.to_numeric(frame["strike"], errors="coerce")
    rows = frame[np.isclose(strike.fillna(float("nan")), float(price), equal_nan=False)]
    if side is not None and "type" in rows.columns:
        rows = rows[rows["type"].astype(str).str.upper() == side]
    return rows


def _single_expiration(rows: pd.DataFrame) -> datetime | None:
    if rows.empty or "expiry" not in rows.columns:
        return None
    expirations = pd.to_datetime(rows["expiry"], errors="coerce").dropna().unique()
    if len(expirations) != 1:
        return None
    return pd.Timestamp(expirations[0]).to_pydatetime()


def _level_metadata(rows: pd.DataFrame, side: str | None) -> dict[str, object]:
    metadata: dict[str, object] = {}
    if side is not None:
        metadata["side"] = side
    if rows.empty or "expiry" not in rows.columns:
        return metadata
    expiration_count = int(pd.to_datetime(rows["expiry"], errors="coerce").dropna().nunique())
    if expiration_count:
        metadata["expiration_count"] = expiration_count
    return metadata


def _metric_maxes(frame: pd.DataFrame) -> dict[str, float]:
    if frame.empty or "strike" not in frame.columns:
        return {"gex": 0.0, "open_interest": 0.0, "volume": 0.0}
    grouped = frame.groupby("strike")
    return {
        "gex": float(grouped["gex"].sum().abs().max()) if "gex" in frame else 0.0,
        "open_interest": float(grouped["open_interest"].sum().max()) if "open_interest" in frame else 0.0,
        "volume": float(grouped["volume"].sum().max()) if "volume" in frame else 0.0,
    }


def _strength(stats: dict[str, float], maxes: dict[str, float]) -> int:
    weights = {"gex": 0.5, "open_interest": 0.3, "volume": 0.2}
    score = 0.0
    used_weight = 0.0
    for metric, weight in weights.items():
        max_value = maxes.get(metric, 0.0)
        if max_value <= 0:
            continue
        score += min(abs(stats[metric]) / max_value, 1.0) * weight
        used_weight += weight
    if used_weight <= 0:
        return 50
    return int(round((score / used_weight) * 100))


def _top_gex_prices(frame: pd.DataFrame, limit: int) -> tuple[float, ...]:
    if limit <= 0 or frame.empty or not {"strike", "gex"}.issubset(frame.columns):
        return ()
    grouped = frame.groupby("strike")["gex"].sum()
    return tuple(float(strike) for strike in grouped.abs().nlargest(limit).index)


def _extreme_gex_price(frame: pd.DataFrame, *, positive: bool) -> float | None:
    """Reuse the existing GEX aggregate to identify positive/negative extremes."""
    if frame.empty or not {"strike", "gex"}.issubset(frame.columns):
        return None
    grouped = frame.groupby("strike")["gex"].sum()
    eligible = grouped[grouped > 0] if positive else grouped[grouped < 0]
    if eligible.empty:
        return None
    return float(eligible.idxmax() if positive else eligible.idxmin())


def _top_metric_price(frame: pd.DataFrame, metric: str) -> float | None:
    if frame.empty or "strike" not in frame.columns or metric not in frame.columns:
        return None
    grouped = frame.groupby("strike")[metric].sum()
    if grouped.empty:
        return None
    return float(grouped.idxmax())


def _sum_column(frame: pd.DataFrame, column: str) -> float:
    if column not in frame:
        return 0.0
    return float(frame[column].fillna(0.0).sum())


def _dedupe_levels(levels: list[MarketLevel]) -> tuple[MarketLevel, ...]:
    by_key: dict[tuple[LevelType, float], MarketLevel] = {}
    for level in levels:
        key = (level.level_type, level.price)
        current = by_key.get(key)
        if current is None or level.strength > current.strength:
            by_key[key] = level
    return tuple(by_key.values())
