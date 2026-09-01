"""Live ingestion loop: APScheduler setup, cadences, and job registration."""
from __future__ import annotations

import logging
import threading
from datetime import datetime, time

from apscheduler.schedulers.background import BackgroundScheduler

from ..cli import backup
from ..infrastructure import rates
from .flush_streams import flush_prices, flush_tape, flush_ticks
from .refresh_market import pull_all, pull_symbol, pull_vix
from .refresh_native import (
    NATIVE_CACHE_FRESH_S,
    native_index_key,
    pull_native_index,
    pull_native_options,
)
from ..calculations.native import build_native_summary
from ..config import SETTINGS
from ..infrastructure.git_repository import push_data_repo
from ..metrics import ET
from ..domain.state import STATE, GlobalState, UnderlyingState

log = logging.getLogger(__name__)

MARKET_OPEN = time(9, 30)
MARKET_CLOSE = time(16, 15)


def market_is_open(now_et: datetime | None = None) -> bool:
    now_et = now_et or datetime.now(ET)
    if now_et.weekday() >= 5:
        return False
    return MARKET_OPEN <= now_et.time() <= MARKET_CLOSE


class _Cadence:
    """Trigger an action every N loop iterations."""

    def __init__(self, interval_s: int | None = None) -> None:
        self.count = 0
        interval_s = SETTINGS.snapshot_interval_s if interval_s is None else interval_s
        self.every = max(1, interval_s // SETTINGS.flow_interval_s)

    def tick(self) -> bool:
        due = self.count % self.every == 0
        self.count += 1
        return due


_CADENCE = _Cadence()
# Constituents follow their own cadence; they rely on daily open interest and do not need the same resolution as targets.
_CONSTITUENT_CADENCE = _Cadence(SETTINGS.constituent_interval_s)
_CONSTITUENT_SNAPSHOT = _Cadence(SETTINGS.constituent_snapshot_interval_s)


def start_scheduler() -> BackgroundScheduler:
    sched = BackgroundScheduler(timezone="America/New_York")
    sched.add_job(
        pull_all,
        "interval",
        seconds=SETTINGS.flow_interval_s,
        max_instances=1,
        coalesce=True,
    )
    # Flush more often than once per minute: bars are written on close, so this bounds data loss on crash.
    sched.add_job(flush_prices, "interval", seconds=30, max_instances=1, coalesce=True)
    sched.add_job(flush_tape, "interval", seconds=30, max_instances=1, coalesce=True)
    # Native NQ/ES options: loose cadence (~90s per cycle), max_instances=1 prevents overlap.
    sched.add_job(pull_native_options, "interval", minutes=15,
                  max_instances=1, coalesce=True)
    # Native index chains: ~20s per chain, much faster than futures—tighter cadence makes sense.
    sched.add_job(pull_native_index, "interval", minutes=3,
                  max_instances=1, coalesce=True)
    # Continuous tick capture (24/5): collector aggregates in memory, this flushes to daily parquet every 60s.
    # Uses a dedicated dxLink session, separate from the dashboard spot feed.
    sched.add_job(flush_ticks, "interval", seconds=60, max_instances=1, coalesce=True)
    sched.add_job(push_data_repo, "cron", day_of_week="mon-fri", hour=16, minute=20)
    # Remote backup after git push: covers large Databento archives (>100MB) GitHub rejects. Logs and exits if rclone not configured.
    sched.add_job(backup.run, "cron", day_of_week="mon-fri", hour=16, minute=30)
    # Risk-free rate: prior day's SOFR published ~8am ET; fetch at 8:15. Weekends use last business day.
    sched.add_job(rates.refresh, "cron", day_of_week="mon-fri", hour=8, minute=15)
    sched.start()
    # Load rate at startup in a background thread; falls back to constant if unavailable.
    threading.Thread(target=rates.refresh, daemon=True).start()
    # Immediate first pull (even outside market hours: shows last known state).
    threading.Thread(target=pull_all, kwargs={"force": True}, daemon=True).start()
    # Same for native NQ/ES: without this, they'd be blank until the first scheduled run (up to 15 min).
    threading.Thread(target=pull_native_options, daemon=True).start()
    threading.Thread(target=pull_native_index, daemon=True).start()
    return sched


__all__ = [
    "ET",
    "MARKET_CLOSE",
    "MARKET_OPEN",
    "NATIVE_CACHE_FRESH_S",
    "STATE",
    "GlobalState",
    "UnderlyingState",
    "_Cadence",
    "build_native_summary",
    "flush_prices",
    "flush_tape",
    "flush_ticks",
    "market_is_open",
    "native_index_key",
    "pull_all",
    "pull_native_index",
    "pull_native_options",
    "pull_symbol",
    "pull_vix",
    "push_data_repo",
    "start_scheduler",
]
