"""Shared Parquet mechanics: atomic writes, locking, dtype normalization."""
from __future__ import annotations

import logging
import os
import threading
import uuid
from pathlib import Path

import pandas as pd

log = logging.getLogger(__name__)


def _data_dir() -> Path:
    """Lazy access to settings data_dir to respect test monkeypatches."""
    from ..config import SETTINGS
    return SETTINGS.data_dir


def _prepare_parquet_df(df: pd.DataFrame) -> pd.DataFrame:
    """Fastparquet is stricter than pyarrow for object columns containing Python dates."""
    out = df.copy()
    for column in out.columns:
        series = out[column]
        if not pd.api.types.is_object_dtype(series):
            continue
        values = series.dropna()
        if values.empty:
            continue
        if all(isinstance(value, (pd.Timestamp,)) for value in values):
            continue
        from datetime import date, datetime
        if all(isinstance(value, (date, datetime)) for value in values):
            out[column] = pd.to_datetime(series, errors="coerce").dt.strftime("%Y-%m-%d")
    return out


def _write_atomic(df: pd.DataFrame, path: Path) -> None:
    """Write to a temporary file and replace the target atomically."""
    safe_df = _prepare_parquet_df(df)
    tmp = path.with_suffix(
        f"{path.suffix}.{os.getpid()}.{threading.get_ident()}"
        f".{uuid.uuid4().hex[:8]}.tmp"
    )
    try:
        safe_df.to_parquet(tmp, index=False)
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


# Public for testing
write_atomic = _write_atomic


_LOCKS: dict[Path, threading.Lock] = {}
_LOCKS_GUARD = threading.Lock()


def _lock_for(path: Path) -> threading.Lock:
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(path, threading.Lock())


def _ensure(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def read_parquet_safe(path: Path) -> pd.DataFrame:
    """Read parquet file, returning empty DataFrame if not found."""
    return pd.read_parquet(path) if path.exists() else pd.DataFrame()


def write_parquet_atomic(df: pd.DataFrame, path: Path) -> None:
    """Atomic write with directory creation."""
    _write_atomic(df, _ensure(path))


def append_parquet_atomic(new_rows: pd.DataFrame, path: Path, dedup_key: str | None = None) -> None:
    """Read-concat-write with optional deduplication, under file lock."""
    lock = _lock_for(path)
    with lock:
        existing = read_parquet_safe(path)
        combined = pd.concat([existing, new_rows], ignore_index=True) if not existing.empty else new_rows
        if dedup_key and not combined.empty:
            combined = combined.drop_duplicates(subset=dedup_key, keep="last").sort_values(dedup_key)
        _write_atomic(combined, _ensure(path))


def append_parquet_atomic_unsorted(new_rows: pd.DataFrame, path: Path) -> None:
    """Read-concat-write without sorting (for simple daily append)."""
    lock = _lock_for(path)
    with lock:
        existing = read_parquet_safe(path)
        combined = pd.concat([existing, new_rows], ignore_index=True) if not existing.empty else new_rows
        _write_atomic(combined, _ensure(path))