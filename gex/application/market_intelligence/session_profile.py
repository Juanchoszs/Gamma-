"""Session profile payloads from normalized price bars."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from gex.domain.market.intelligence import (
    LevelSource,
    LevelType,
    MarketLevel,
    SessionType,
)


@dataclass(frozen=True)
class SessionProfileConfig:
    timezone: str = "America/New_York"
    regular_start: time = time(9, 30)
    regular_end: time = time(16, 0)
    value_area_fraction: float = 0.70
    price_bin_size: float | None = None

    def __post_init__(self) -> None:
        if not 0 < self.value_area_fraction <= 1:
            raise ValueError("value_area_fraction must be in (0, 1]")
        if self.price_bin_size is not None and self.price_bin_size <= 0:
            raise ValueError("price_bin_size must be positive")


def build_session_profile_payload(
    *,
    symbol: str,
    timestamp: datetime,
    prices: pd.DataFrame,
    as_of: datetime | None = None,
    config: SessionProfileConfig | None = None,
) -> dict[str, Any]:
    """Build regular and overnight session levels from candle data.

    The function consumes already-loaded bars. It does not read storage, fetch
    market data, or infer missing candles.
    """
    cfg = config or SessionProfileConfig()
    tz = ZoneInfo(cfg.timezone)
    effective_as_of = _as_tz(as_of or timestamp, tz)
    frame = _normalized_prices(prices, tz, effective_as_of)
    local_day = effective_as_of.date()

    regular = _profile(
        "REGULAR",
        _regular_bars(frame, local_day, cfg),
        cfg,
    )
    overnight = _profile(
        "OVERNIGHT",
        _overnight_bars(frame, local_day, cfg),
        cfg,
    )

    return {
        "symbol": symbol,
        "timestamp": effective_as_of.isoformat(),
        "timezone": cfg.timezone,
        "as_of": effective_as_of.isoformat(),
        "sessions": {
            "regular": regular,
            "overnight": overnight,
        },
        "methodology": {
            "regular_window": f"{cfg.regular_start.isoformat()}-{cfg.regular_end.isoformat()}",
            "overnight_window": "previous regular close to current regular open",
            "value_area_fraction": cfg.value_area_fraction,
            "poc": "Price bin with the highest available bar weight.",
            "value_area": "Highest-weight price bins accumulated until the configured value-area fraction is reached.",
        },
    }


def build_session_levels_from_profile(profile: dict[str, Any]) -> tuple[MarketLevel, ...]:
    """Convert session profile output into unified market levels."""
    timestamp = _parse_iso_datetime(str(profile["timestamp"]))
    levels: list[MarketLevel] = []
    sessions = profile.get("sessions", {})
    regular = sessions.get("regular", {})
    overnight = sessions.get("overnight", {})

    levels.extend(_profile_levels(
        profile=regular,
        timestamp=timestamp,
        session=SessionType.REGULAR,
        mappings={
            "poc": LevelType.POC,
            "vah": LevelType.VAH,
            "val": LevelType.VAL,
        },
    ))
    levels.extend(_profile_levels(
        profile=overnight,
        timestamp=timestamp,
        session=SessionType.OVERNIGHT,
        mappings={
            "high": LevelType.OVH,
            "low": LevelType.OVL,
            "poc": LevelType.POC,
            "vah": LevelType.VAH,
            "val": LevelType.VAL,
        },
    ))
    return tuple(levels)


def _normalized_prices(prices: pd.DataFrame, tz: ZoneInfo, as_of: datetime) -> pd.DataFrame:
    required = {"timestamp", "open", "high", "low", "close"}
    if prices is None or prices.empty or not required.issubset(prices.columns):
        return pd.DataFrame(columns=[*required, "volume", "ticks", "_local_ts"])

    frame = prices.copy()
    for column in ("open", "high", "low", "close", "volume", "ticks"):
        if column in frame:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.dropna(subset=["timestamp", "open", "high", "low", "close"])
    if frame.empty:
        return pd.DataFrame(columns=[*required, "volume", "ticks", "_local_ts"])

    local_ts = pd.to_datetime(frame["timestamp"], errors="coerce")
    if getattr(local_ts.dt, "tz", None) is None:
        local_ts = local_ts.dt.tz_localize(tz, ambiguous="NaT", nonexistent="shift_forward")
    else:
        local_ts = local_ts.dt.tz_convert(tz)
    frame["_local_ts"] = local_ts
    frame = frame.dropna(subset=["_local_ts"]).sort_values("_local_ts")
    frame = frame[frame["_local_ts"] <= pd.Timestamp(as_of)]
    return frame


def _regular_bars(frame: pd.DataFrame, local_day, cfg: SessionProfileConfig) -> pd.DataFrame:
    if frame.empty:
        return frame
    ts = frame["_local_ts"]
    return frame[
        (ts.dt.date == local_day)
        & (ts.dt.time >= cfg.regular_start)
        & (ts.dt.time <= cfg.regular_end)
    ]


def _overnight_bars(frame: pd.DataFrame, local_day, cfg: SessionProfileConfig) -> pd.DataFrame:
    if frame.empty:
        return frame
    tz = frame["_local_ts"].dt.tz
    start = datetime.combine(local_day - timedelta(days=1), cfg.regular_end, tzinfo=tz)
    end = datetime.combine(local_day, cfg.regular_start, tzinfo=tz)
    ts = frame["_local_ts"]
    return frame[(ts > pd.Timestamp(start)) & (ts < pd.Timestamp(end))]


def _profile(name: str, bars: pd.DataFrame, cfg: SessionProfileConfig) -> dict[str, Any]:
    if bars.empty:
        return {
            "session": name,
            "available": False,
            "bar_count": 0,
            "levels": {},
        }

    ordered = bars.sort_values("_local_ts")
    weight_col = _weight_column(ordered)
    levels = {
        "open": float(ordered["open"].iloc[0]),
        "high": float(ordered["high"].max()),
        "low": float(ordered["low"].min()),
        "close": float(ordered["close"].iloc[-1]),
    }
    profile_levels = _volume_profile_levels(ordered, cfg, weight_col)
    levels.update(profile_levels)
    return {
        "session": name,
        "available": True,
        "start": ordered["_local_ts"].iloc[0].isoformat(),
        "end": ordered["_local_ts"].iloc[-1].isoformat(),
        "bar_count": int(len(ordered)),
        "weight": weight_col,
        "levels": {key: value for key, value in levels.items() if value is not None},
    }


def _weight_column(bars: pd.DataFrame) -> str:
    if "volume" in bars.columns and float(bars["volume"].fillna(0).sum()) > 0:
        return "volume"
    if "ticks" in bars.columns and float(bars["ticks"].fillna(0).sum()) > 0:
        return "ticks"
    return "bar_count"


def _volume_profile_levels(
    bars: pd.DataFrame,
    cfg: SessionProfileConfig,
    weight_col: str,
) -> dict[str, float | None]:
    prices = bars["close"].astype(float)
    bin_size = cfg.price_bin_size or _auto_bin_size(bars)
    if bin_size <= 0:
        return {"poc": None, "vah": None, "val": None}
    bins = (prices / bin_size).round() * bin_size
    weights = (
        bars[weight_col].fillna(0).astype(float)
        if weight_col in bars.columns
        else pd.Series(1.0, index=bars.index)
    )
    profile = weights.groupby(bins).sum().sort_index()
    profile = profile[profile > 0]
    if profile.empty:
        return {"poc": None, "vah": None, "val": None}

    poc = float(profile.idxmax())
    target = float(profile.sum()) * cfg.value_area_fraction
    selected: list[float] = []
    running = 0.0
    for price, weight in profile.sort_values(ascending=False).items():
        selected.append(float(price))
        running += float(weight)
        if running >= target:
            break
    return {
        "poc": poc,
        "vah": max(selected),
        "val": min(selected),
    }


def _auto_bin_size(bars: pd.DataFrame) -> float:
    low = float(bars["low"].min())
    high = float(bars["high"].max())
    span = high - low
    if span <= 0:
        return max(round(high * 0.0001, 2), 0.01)
    raw = span / 40.0
    if raw >= 10:
        return round(raw)
    if raw >= 1:
        return round(raw, 1)
    return max(round(raw, 2), 0.01)


def _as_tz(value: datetime, tz: ZoneInfo) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=tz)
    return value.astimezone(tz)


def _profile_levels(
    *,
    profile: dict[str, Any],
    timestamp: datetime,
    session: SessionType,
    mappings: dict[str, LevelType],
) -> tuple[MarketLevel, ...]:
    if not profile or not profile.get("available"):
        return ()
    raw_levels = profile.get("levels", {})
    output: list[MarketLevel] = []
    for key, level_type in mappings.items():
        price = raw_levels.get(key)
        if price is None:
            continue
        output.append(MarketLevel(
            id=f"{session.value}-{level_type.value}-{float(price):g}",
            level_type=level_type,
            price=float(price),
            source=LevelSource.SESSION_PROFILE,
            timestamp=timestamp,
            strength=_session_level_strength(key, int(profile.get("bar_count", 0) or 0)),
            session=session,
            metadata={
                "profile_key": key,
                "weight": profile.get("weight"),
                "bar_count": profile.get("bar_count"),
                "start": profile.get("start"),
                "end": profile.get("end"),
            },
        ))
    return tuple(output)


def _session_level_strength(key: str, bar_count: int) -> int:
    base = {
        "poc": 78,
        "vah": 70,
        "val": 70,
        "high": 72,
        "low": 72,
    }.get(key, 65)
    maturity_bonus = min(max(bar_count - 1, 0), 20)
    return min(base + maturity_bonus, 95)


def _parse_iso_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value)
