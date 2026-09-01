"""Domain models for the GEX Dashboard.

Pure domain models without dependencies on:
- Dash/Flask
- APScheduler
- dxFeed/CBOE
- Parquet filesystem
- HTTP
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional
import pandas as pd

from .quality import DataQuality
from .market_state import MarketDataState

# Re-export domain types for convenience.
__all__ = [
    "DataQuality",
    "MarketDataState",
    "ChainSnapshot",
    "SummaryMetrics",
    "SnapshotMetadata",
]


@dataclass
class ChainSnapshot:
    """Normalized option chain snapshot from a data provider."""
    symbol: str
    spot: float
    feed_timestamp: datetime
    fetched_at: datetime
    options: pd.DataFrame
    data_quality: DataQuality = DataQuality.VALID
    age_seconds: Optional[float] = None


@dataclass
class SummaryMetrics:
    """Summary metrics computed from an enriched option chain."""
    timestamp: datetime
    symbol: str
    spot: float
    net_gex: float
    zero_gamma: Optional[float]
    pc_oi: float
    pc_volume: float
    net_gex_0dte: float = 0.0
    basis: Optional[float] = None
    net_dex: Optional[float] = None
    source: str = "cboe"
    data_quality: DataQuality = DataQuality.VALID
    age_seconds: Optional[float] = None

    def as_row(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "symbol": self.symbol,
            "spot": self.spot,
            "net_gex": self.net_gex,
            "zero_gamma": self.zero_gamma,
            "pc_oi": self.pc_oi,
            "pc_volume": self.pc_volume,
            "net_gex_0dte": self.net_gex_0dte,
            "basis": self.basis,
            "net_dex": self.net_dex,
            "source": self.source,
            "data_quality": self.data_quality.value,
            "age_seconds": self.age_seconds,
        }


@dataclass
class SnapshotMetadata:
    """Metadata stored with each snapshot for traceability."""
    symbol: str
    captured_at: datetime
    source: str
    snapshot_type: str  # LIVE, MARKET_CLOSE, HISTORICAL, EXPIRED
    data_quality: DataQuality
    schema_version: int = 1
    market_state: MarketDataState = MarketDataState.LIVE
    age_seconds: Optional[float] = None
    provider_timestamp: Optional[datetime] = None