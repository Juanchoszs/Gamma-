"""History persistence: daily summary metrics and context indices."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

from .parquet import append_parquet_atomic, read_parquet_safe


def _data_dir() -> Path:
    from ..config import SETTINGS
    return SETTINGS.data_dir


def _history_path() -> Path:
    return _data_dir() / "history" / "metrics.parquet"


def _index_spot_path(key: str) -> Path:
    return _data_dir() / "history" / f"{key}.parquet"


def append_history(row: dict) -> Path:
    """Append a summary row to the shared history file (concurrent writers)."""
    new = pd.DataFrame([row])
    append_parquet_atomic(new, _history_path())
    return _history_path()


def load_history(symbol: str | None = None) -> pd.DataFrame:
    """Load history, optionally filtered by symbol."""
    df = read_parquet_safe(_history_path())
    return df[df["symbol"] == symbol] if symbol and not df.empty else df


def append_index_spot(key: str, row: dict) -> Path:
    """Append a context index spot (e.g., VIX) to its dedicated file."""
    path = _index_spot_path(key)
    new = pd.DataFrame([row])
    append_parquet_atomic(new, path)
    return path


def load_index_spot(key: str) -> pd.DataFrame:
    """Load context index history."""
    return read_parquet_safe(_index_spot_path(key))


def previous_close_spot(symbol: str, day: str | None = None) -> float | None:
    """Previous close spot for `day` from history metrics."""
    from ..metrics import ET

    day = day or datetime.now(ET).strftime("%Y-%m-%d")
    h = load_history(symbol)
    if h.empty or "spot" not in h.columns:
        return None
    ts = pd.to_datetime(h["timestamp"])
    prev = h[ts.dt.strftime("%Y-%m-%d") < day].sort_values("timestamp")
    return float(prev["spot"].iloc[-1]) if not prev.empty else None