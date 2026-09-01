"""Drain in-memory market streams onto disk."""
from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from ..providers import flowtape
from . import roll
from .. import store
from ..metrics import ET
from gex.providers.rtquote import PUBLIC_QUOTES, QUOTES
from gex.providers.tickcapture import CAPTURE

log = logging.getLogger(__name__)


def _flush_bars(bars: list, source: str) -> None:
    """Write completed 1-min bars to disk, regardless of source (broker or delayed public fallback)."""
    if not bars:
        return
    by_symbol: dict[str, list[dict]] = {}
    for symbol, bar in bars:
        ts = datetime.fromtimestamp(bar.minute, tz=UTC).astimezone(ET).replace(tzinfo=None)
        by_symbol.setdefault(symbol, []).append({
            "timestamp": ts, "open": bar.open, "high": bar.high,
            "low": bar.low, "close": bar.close, "ticks": bar.ticks,
            "source": source,
        })
    for symbol, rows in by_symbol.items():
        try:
            store.append_prices(symbol, rows, rows[0]["timestamp"])
        except Exception:  # noqa: BLE001 — a write failure must not break anything
            log.exception("Failed to write prices for %s", symbol)


def flush_prices() -> None:
    """Write completed 1-min bars from the real-time feed.

    Without broker credentials, `QUOTES.drain_bars()` returns an empty list.
    `PUBLIC_QUOTES` (the free delayed NQ/ES fallback) also builds bars the same way
    and must be drained too: otherwise its bars accumulate in memory and the heatmap
    falls back to coarse snapshot resolution (~10 min) even when delayed data is available.

    Source tagged at write time: `"dxfeed"` (broker, personal use only) or
    `"dxfeed_public"` (public demo, ~15-20 min delay) — both excluded from export by default
    (see gex/export.py), but kept distinct to avoid conflation.
    """
    _flush_bars(QUOTES.drain_bars(), "dxfeed")
    _flush_bars(PUBLIC_QUOTES.drain_bars(), "dxfeed_public")


def flush_tape() -> None:
    """Write completed signed order-flow bars (see gex/flowtape.py).

    Same logic as `flush_prices`: the collector aggregates in memory; only completed 1-min bars hit disk.
    """
    bars = flowtape.TAPE.drain_bars()
    if not bars:
        return
    by_symbol: dict[str, list[dict]] = {}
    for symbol, bar in bars:
        ts = datetime.fromtimestamp(bar.minute, tz=UTC).astimezone(ET).replace(tzinfo=None)
        by_symbol.setdefault(symbol, []).append(bar.as_row(symbol, ts))
    for symbol, rows in by_symbol.items():
        try:
            store.append_tape(symbol, rows, rows[0]["timestamp"])
        except Exception:  # noqa: BLE001 — a write failure must not break anything
            log.exception("Failed to write order flow for %s", symbol)


def flush_ticks() -> None:
    """Write raw tick-by-tick data accumulated by the continuous capture (see gex/tickcapture).

    Same logic as flush_prices/flush_tape: collector aggregates in memory, flush writes to disk.
    Each tick is filed by its CME SESSION date, defined in NEW YORK TIME:
    18:00 ET (open) -> 16:59 ET (close) of the next day, i.e. `date = (ET + 6h).date()`.

    Do NOT use Paris time: it equals ET+6 only when both zones are on summer time.
    During DST transitions (~3 weeks/year), the offset drops to 5h, cutting the session wrong.
    ET is the only stable reference because it is the market's own timezone.
    """
    buf = CAPTURE.drain()
    for symbol, per_contract in buf.items():
        # 1. Group by (session, contract) and accumulate volume for EACH
        #    contract — including the one we won't write: this is used to pick the dominant for the next session (see gex/roll).
        by_day: dict[str, dict[str, list]] = {}
        volumes: dict[str, dict[str, float]] = {}
        for contract, rows in per_contract.items():
            for r in rows:
                # +6h: 18:00 ET (open) rolls over to midnight, so the resulting date IS the session date, including the evening portion.
                sess = (datetime.fromtimestamp(r["ts"], tz=UTC).astimezone(ET)
                        + timedelta(hours=6))
                day = sess.strftime("%Y-%m-%d")
                by_day.setdefault(day, {}).setdefault(contract, []).append((sess, r))
                volumes.setdefault(day, {})[contract] = (
                    volumes.setdefault(day, {}).get(contract, 0) + (r.get("volume") or 0))

        for day, per_c in by_day.items():
            try:
                roll.record_volumes(symbol, day, volumes.get(day, {}))
            except Exception:  # noqa: BLE001 — roll state must not block anything
                log.exception("Tick capture: failed to record volumes for %s", symbol)
            # 2. Only write the dominant contract: keeps the on-disk series
            #    continuous, comparable to the reference dataset.
            #    Broker order ([active, next]) is used as fallback when no prior-day volume is known.
            contracts = [c for c in CAPTURE.contract_order(symbol) if c in per_c]
            contracts += [c for c in per_c if c not in contracts]
            keep = roll.dominant(symbol, day, contracts)
            items = per_c.get(keep) or []
            if not items:
                continue
            rows_day = [it[1] for it in items]
            try:
                store.append_ticks(symbol, rows_day, items[0][0])
            except Exception:  # noqa: BLE001 — a write failure must not break anything
                log.exception("Tick capture: write failed for %s", symbol)
