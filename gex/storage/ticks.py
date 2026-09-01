"""Tick persistence: raw transaction ticks."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

from .parquet import append_parquet_atomic, read_parquet_safe


def _data_dir() -> Path:
    from ..config import SETTINGS
    return SETTINGS.data_dir


def _ticks_path(symbol: str, ts: datetime) -> Path:
    return _data_dir() / "ticks" / symbol / f"{ts:%Y-%m-%d}.parquet"


def append_ticks(symbol: str, rows: list[dict], ts: datetime) -> Path | None:
    """Append raw ticks to the symbol's daily parquet."""
    if not rows:
        return None
    path = _ticks_path(symbol, ts)
    new = pd.DataFrame(rows)
    append_parquet_atomic(new, path)
    return path


def load_ticks(symbol: str, day: str) -> pd.DataFrame:
    """Load raw ticks for a symbol/day."""
    path = _data_dir() / "ticks" / symbol / f"{day}.parquet"
    return read_parquet_safe(path)