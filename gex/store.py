"""Parquet persistence facade — re-exports from storage submodules.

This module preserves the original `gex.store` import surface while delegating
to the separated storage layer in `gex.storage.*`.
"""
from __future__ import annotations

from .storage.parquet import write_atomic as _write_atomic
from .storage.snapshots import (
    save_snapshot,
    load_last_snapshot,
    load_snapshot_near,
    load_latest_snapshot,
    load_first_snapshot,
    load_day_snapshots,
    load_previous_snapshot,
    snapshot_days,
)

from .storage.history import (
    append_history,
    load_history,
    append_index_spot,
    load_index_spot,
    previous_close_spot,
)

from .storage.prices import (
    append_prices,
    load_prices,
    price_days,
)

from .storage.flow import (
    append_daily_flows as _append_daily_flows,
    load_flows,
    append_tape,
    load_tape,
    tape_days,
)

from .storage.ticks import (
    append_ticks,
    load_ticks,
)


def append_daily(kind: str, symbol: str, row: dict, ts) -> str:
    """Compatibility shim: only `kind='flows'` is supported in the new layer."""
    if kind != "flows":
        raise ValueError(f"append_daily: unsupported kind={kind!r}, only 'flows' is supported")
    return _append_daily_flows(symbol, row, ts)


__all__ = [
    "save_snapshot",
    "append_daily",
    "append_history",
    "append_index_spot",
    "load_index_spot",
    "append_prices",
    "previous_close_spot",
    "price_days",
    "load_prices",
    "append_ticks",
    "load_ticks",
    "append_tape",
    "load_tape",
    "tape_days",
    "load_flows",
    "snapshot_days",
    "load_last_snapshot",
    "load_snapshot_near",
    "load_latest_snapshot",
    "load_first_snapshot",
    "load_day_snapshots",
    "load_previous_snapshot",
    "load_history",
    "_write_atomic",
]