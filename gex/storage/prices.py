"""Price persistence: 1-minute OHLCV candles."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

from .parquet import append_parquet_atomic, read_parquet_safe


def _data_dir() -> Path:
    from ..config import SETTINGS
    return SETTINGS.data_dir


def _prices_path(symbol: str, ts: datetime) -> Path:
    return _data_dir() / "prices" / symbol / f"{ts:%Y-%m-%d}.parquet"


def append_prices(symbol: str, rows: list[dict], ts: datetime) -> Path:
    """Append 1-min candles to the daily file with timestamp deduplication."""
    if not rows:
        return _prices_path(symbol, ts)
    path = _prices_path(symbol, ts)
    new = pd.DataFrame(rows)
    new = new.drop_duplicates(subset="timestamp", keep="last").sort_values("timestamp")
    append_parquet_atomic(new, path, dedup_key="timestamp")
    return path


def load_prices(symbol: str, day: str) -> pd.DataFrame:
    """Load candles for a symbol/day."""
    path = _data_dir() / "prices" / symbol / f"{day}.parquet"
    return read_parquet_safe(path)


def price_days(symbol: str) -> list[str]:
    """Days (YYYY-MM-DD) for which candle files exist."""
    root = _data_dir() / "prices" / symbol
    if not root.exists():
        return []
    return sorted(p.stem for p in root.glob("*.parquet"))