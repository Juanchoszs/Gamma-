"""Snapshot persistence: enriched option chains with metadata."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

from .parquet import write_parquet_atomic


def _data_dir() -> Path:
    from ..config import SETTINGS
    return SETTINGS.data_dir


def _snapshot_path(symbol: str, ts: datetime) -> Path:
    return _data_dir() / "snapshots" / symbol / ts.strftime("%Y-%m-%d") / f"{ts:%H%M%S}.parquet"


def save_snapshot(
    symbol: str,
    df: pd.DataFrame,
    ts: datetime,
    source: str = "cboe",
    snapshot_type: str = "LIVE",
    data_quality: str = "VALID",
    market_state: str = "LIVE",
    age_seconds: float | None = None,
    provider_timestamp: datetime | None = None,
    schema_version: int = 1,
) -> Path:
    """Save enriched chain snapshot with metadata columns."""
    df = df.copy()
    df["_snapshot_meta_symbol"] = symbol
    df["_snapshot_meta_captured_at"] = ts
    df["_snapshot_meta_source"] = source
    df["_snapshot_meta_type"] = snapshot_type
    df["_snapshot_meta_quality"] = data_quality
    df["_snapshot_meta_schema_version"] = schema_version
    df["_snapshot_meta_market_state"] = market_state
    df["_snapshot_meta_age_seconds"] = age_seconds
    df["_snapshot_meta_provider_ts"] = provider_timestamp

    path = _snapshot_path(symbol, ts)
    write_parquet_atomic(df, path)
    return path


def load_last_snapshot(symbol: str, day: str) -> pd.DataFrame | None:
    """Last chain snapshot for a given day."""
    root = _data_dir() / "snapshots" / symbol / day
    files = sorted(root.glob("*.parquet")) if root.exists() else []
    return pd.read_parquet(files[-1]) if files else None


def load_snapshot_near(symbol: str, day: str, target_hhmmss: str = "160000") -> pd.DataFrame | None:
    """Chain snapshot closest to a target time (default 16:00 ET = cash close)."""
    root = _data_dir() / "snapshots" / symbol / day
    files = sorted(root.glob("*.parquet")) if root.exists() else []
    if not files:
        return None

    def _secs(stem: str) -> int:
        try:
            return int(stem[0:2]) * 3600 + int(stem[2:4]) * 60 + int(stem[4:6])
        except (ValueError, IndexError):
            return 0

    target = _secs(target_hhmmss)
    best = min(files, key=lambda f: abs(_secs(f.stem) - target))
    return pd.read_parquet(best)


def load_latest_snapshot(symbol: str) -> tuple[pd.DataFrame, datetime] | None:
    """Latest snapshot across all sessions, with its ET timestamp."""
    root = _data_dir() / "snapshots" / symbol
    days = sorted(d.name for d in root.iterdir() if d.is_dir() and any(d.glob("*.parquet"))) if root.exists() else []
    if not days:
        return None
    day = days[-1]
    files = sorted((root / day).glob("*.parquet"))
    if not files:
        return None
    f = files[-1]
    try:
        ts = datetime.strptime(f"{day} {f.stem}", "%Y-%m-%d %H%M%S")
    except ValueError:
        return None
    return pd.read_parquet(f), ts


def load_first_snapshot(symbol: str, day: str) -> pd.DataFrame | None:
    """First session snapshot — the one on which a plan is built."""
    root = _data_dir() / "snapshots" / symbol / day
    files = sorted(root.glob("*.parquet")) if root.exists() else []
    return pd.read_parquet(files[0]) if files else None


def load_day_snapshots(
    symbol: str, day: str, columns: list[str] | None = None
) -> list[tuple[datetime, pd.DataFrame]]:
    """All snapshots for a session, timestamped from filename."""
    root = _data_dir() / "snapshots" / symbol / day
    if not root.exists():
        return []
    out = []
    for f in sorted(root.glob("*.parquet")):
        try:
            ts = datetime.strptime(f"{day} {f.stem}", "%Y-%m-%d %H%M%S")
        except ValueError:
            continue
        cols = columns
        if cols is not None:
            import pyarrow.parquet as pq
            have = set(pq.ParquetFile(f).schema_arrow.names)
            cols = [c for c in columns if c in have]
        out.append((ts, pd.read_parquet(f, columns=cols)))
    return out


def load_previous_snapshot(symbol: str, before_day: str) -> tuple[str, pd.DataFrame] | None:
    """Last snapshot from the session before `before_day` (day + data)."""
    root = _data_dir() / "snapshots" / symbol
    days = sorted(d.name for d in root.iterdir() if d.is_dir() and d.name < before_day) if root.exists() else []
    if not days:
        return None
    prev = days[-1]
    df = load_last_snapshot(symbol, prev)
    return (prev, df) if df is not None else None


def snapshot_days(symbol: str) -> list[str]:
    """Days (YYYY-MM-DD) for which at least one snapshot exists."""
    root = _data_dir() / "snapshots" / symbol
    if not root.exists():
        return []
    return sorted(d.name for d in root.iterdir() if d.is_dir() and any(d.glob("*.parquet")))