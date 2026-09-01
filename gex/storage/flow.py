"""Flow persistence: CBOE proxy flows and broker-signed tape."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

from .parquet import append_parquet_atomic, read_parquet_safe


def _data_dir() -> Path:
    from ..config import SETTINGS
    return SETTINGS.data_dir


def _flows_path(symbol: str, ts: datetime) -> Path:
    return _data_dir() / "flows" / symbol / f"{ts:%Y-%m-%d}.parquet"


def _tape_path(symbol: str, ts: datetime) -> Path:
    return _data_dir() / "tape" / symbol / f"{ts:%Y-%m-%d}.parquet"


def append_daily_flows(symbol: str, row: dict, ts: datetime) -> Path:
    """Append CBOE proxy flow (redistributable) to daily file."""
    path = _flows_path(symbol, ts)
    new = pd.DataFrame([row])
    append_parquet_atomic(new, path)
    return path


def load_flows(symbol: str, day: str) -> pd.DataFrame:
    """Load CBOE proxy flows for a symbol/day."""
    path = _data_dir() / "flows" / symbol / f"{day}.parquet"
    return read_parquet_safe(path)


def append_tape(symbol: str, rows: list[dict], ts: datetime) -> Path:
    """Append signed order-flow bars (1 min) to daily file with dedup."""
    if not rows:
        return _tape_path(symbol, ts)
    path = _tape_path(symbol, ts)
    new = pd.DataFrame(rows)
    new = new.drop_duplicates(subset="timestamp", keep="last").sort_values("timestamp")
    append_parquet_atomic(new, path, dedup_key="timestamp")
    return path


def load_tape(symbol: str, day: str) -> pd.DataFrame:
    """Load signed tape for a symbol/day."""
    path = _data_dir() / "tape" / symbol / f"{day}.parquet"
    return read_parquet_safe(path)


def tape_days(symbol: str) -> list[str]:
    """Days (YYYY-MM-DD) for which tape files exist."""
    root = _data_dir() / "tape" / symbol
    if not root.exists():
        return []
    return sorted(p.stem for p in root.glob("*.parquet"))