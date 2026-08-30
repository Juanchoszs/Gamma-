"""Market state models for explicit market data states."""
from __future__ import annotations

from enum import Enum
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")


class MarketDataState(Enum):
    """Explicit market data states for UI and API.

    LIVE           - Data is current and actively updated
    DELAYED        - Data is available but delayed
    MARKET_CLOSED  - Market is closed; displayed info from latest valid snapshot
    HISTORICAL     - User is viewing a historical snapshot
    NO_DATA        - No valid market data available
    """
    LIVE = "LIVE"
    DELAYED = "DELAYED"
    MARKET_CLOSED = "MARKET_CLOSED"
    HISTORICAL = "HISTORICAL"
    NO_DATA = "NO_DATA"


@dataclass
class MarketSchedule:
    """US market schedule configuration."""
    open_time: time = time(9, 30)
    close_time: time = time(16, 15)
    timezone: str = "America/New_York"


DEFAULT_SCHEDULE = MarketSchedule()


@dataclass
class MarketStateContext:
    """Context for market state resolution."""
    is_market_open: bool
    current_time_et: datetime
    provider: str
    data_age_seconds: Optional[float]
    data_quality: Optional["DataQuality"]
    snapshot_timestamp: Optional[datetime]
    is_historical_view: bool = False


def is_market_open(now_et: Optional[datetime] = None) -> bool:
    """Check if US market is currently open."""
    now_et = now_et or datetime.now(ET)
    if now_et.weekday() >= 5:  # Saturday = 5, Sunday = 6
        return False
    return DEFAULT_SCHEDULE.open_time <= now_et.time() <= DEFAULT_SCHEDULE.close_time


def resolve_market_state(context: MarketStateContext) -> MarketDataState:
    """Centralized market state resolution.

    This is the single authoritative function for determining
    market data state. All interfaces (API, Dashboard, MCP)
    should use this function.

    Args:
        context: Full context for state resolution

    Returns:
        MarketDataState enum value
    """
    if context.is_historical_view:
        return MarketDataState.HISTORICAL

    if context.data_quality is not None:
        from .quality import DataQuality
        if context.data_quality == DataQuality.NO_DATA:
            return MarketDataState.NO_DATA
        if context.data_quality == DataQuality.INVALID:
            return MarketDataState.NO_DATA

    if context.is_market_open:
        if context.data_quality is not None:
            from .quality import DataQuality
            if context.data_quality == DataQuality.VALID:
                return MarketDataState.LIVE
            elif context.data_quality == DataQuality.WARNING:
                return MarketDataState.DELAYED
            elif context.data_quality in (DataQuality.STALE, DataQuality.EXPIRED):
                return MarketDataState.STALE
        # Default for open market with no explicit quality
        return MarketDataState.LIVE
    else:
        # Market closed - check if we have a valid snapshot
        if context.snapshot_timestamp is not None:
            return MarketDataState.MARKET_CLOSED
        elif context.data_quality is not None:
            from .quality import DataQuality
            if context.data_quality in (DataQuality.VALID, DataQuality.WARNING):
                return MarketDataState.MARKET_CLOSED
        return MarketDataState.NO_DATA