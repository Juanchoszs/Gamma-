"""Diagnostics and data-freshness helpers for market intelligence."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Mapping


class DataFreshness(StrEnum):
    LIVE = "LIVE"
    DELAYED = "DELAYED"
    DATA_STALE = "DATA_STALE"
    DISCONNECTED = "DISCONNECTED"


@dataclass(frozen=True)
class DataFreshnessConfig:
    live_after_seconds: int = 120
    stale_after_seconds: int = 900

    def __post_init__(self) -> None:
        if self.live_after_seconds < 0:
            raise ValueError("live_after_seconds must be non-negative")
        if self.stale_after_seconds < self.live_after_seconds:
            raise ValueError("stale_after_seconds must be greater than or equal to live_after_seconds")


@dataclass(frozen=True)
class SymbolDiagnostics:
    symbol: str
    available: bool
    data_status: DataFreshness
    last_update: datetime | None = None
    age_seconds: float | None = None
    options_count: int = 0
    expiration_count: int = 0
    strike_count: int = 0
    source: str | None = None
    last_error: str | None = None
    quality: Mapping[str, int] = field(default_factory=dict)
    calculation_ms: float | None = None
    last_calculation: datetime | None = None

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "symbol": self.symbol,
            "available": self.available,
            "data_status": self.data_status.value,
            "options_count": self.options_count,
            "expiration_count": self.expiration_count,
            "strike_count": self.strike_count,
        }
        if self.last_update is not None:
            payload["last_update"] = self.last_update.isoformat()
        if self.age_seconds is not None:
            payload["age_seconds"] = round(self.age_seconds, 3)
        if self.source:
            payload["source"] = self.source
        if self.last_error:
            payload["last_error"] = self.last_error
        if self.quality:
            payload["quality"] = dict(self.quality)
        if self.calculation_ms is not None:
            payload["calculation_ms"] = round(self.calculation_ms, 3)
        if self.last_calculation is not None:
            payload["last_calculation"] = self.last_calculation.isoformat()
        return payload


def classify_data_freshness(
    last_update: datetime | None,
    *,
    now: datetime,
    config: DataFreshnessConfig | None = None,
) -> tuple[DataFreshness, float | None]:
    """Classify data freshness from timestamps without guessing market direction."""
    cfg = config or DataFreshnessConfig()
    if last_update is None:
        return DataFreshness.DISCONNECTED, None
    age = max(_age_seconds(last_update, now), 0.0)
    if age <= cfg.live_after_seconds:
        return DataFreshness.LIVE, age
    if age <= cfg.stale_after_seconds:
        return DataFreshness.DELAYED, age
    return DataFreshness.DATA_STALE, age


def build_symbol_diagnostics(
    *,
    symbol: str,
    last_update: datetime | None,
    options_count: int = 0,
    expiration_count: int = 0,
    strike_count: int = 0,
    source: str | None = None,
    last_error: str | None = None,
    quality: Mapping[str, int] | None = None,
    calculation_ms: float | None = None,
    last_calculation: datetime | None = None,
    now: datetime,
    config: DataFreshnessConfig | None = None,
) -> SymbolDiagnostics:
    """Build one symbol diagnostics payload from already-collected state."""
    status, age = classify_data_freshness(last_update, now=now, config=config)
    return SymbolDiagnostics(
        symbol=symbol,
        available=last_update is not None and options_count > 0,
        data_status=status,
        last_update=last_update,
        age_seconds=age,
        options_count=max(int(options_count), 0),
        expiration_count=max(int(expiration_count), 0),
        strike_count=max(int(strike_count), 0),
        source=source,
        last_error=last_error,
        quality=dict(quality or {}),
        calculation_ms=calculation_ms,
        last_calculation=last_calculation,
    )


def diagnostics_payload(
    symbols: tuple[SymbolDiagnostics, ...],
    *,
    api_status: str = "OK",
    websocket_status: str = "UNKNOWN",
    last_error: str | None = None,
    metadata: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Create an API-ready diagnostics object for the current backend state."""
    payload: dict[str, object] = {
        "api_status": api_status,
        "websocket_status": websocket_status,
        "symbols": [symbol.to_dict() for symbol in symbols],
    }
    if last_error:
        payload["last_error"] = last_error
    if metadata:
        payload["metadata"] = dict(metadata)
    return payload


def _age_seconds(last_update: datetime, now: datetime) -> float:
    if last_update.tzinfo is None and now.tzinfo is not None:
        now = now.replace(tzinfo=None)
    elif last_update.tzinfo is not None and now.tzinfo is None:
        last_update = last_update.replace(tzinfo=None)
    return (now - last_update).total_seconds()
