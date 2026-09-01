"""In-memory dashboard state for live snapshots and summaries."""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime

import pandas as pd

from .models import ChainSnapshot
from ..metrics import SummaryMetrics


@dataclass
class UnderlyingState:
    snapshot: ChainSnapshot | None = None
    enriched: pd.DataFrame | None = None
    summary: SummaryMetrics | None = None
    last_feed_ts: datetime | None = None


@dataclass
class GlobalState:
    lock: threading.Lock = field(default_factory=threading.Lock)
    per_symbol: dict[str, UnderlyingState] = field(default_factory=dict)
    last_error: str | None = None

    def get(self, symbol: str) -> UnderlyingState:
        return self.per_symbol.setdefault(symbol, UnderlyingState())


STATE = GlobalState()
