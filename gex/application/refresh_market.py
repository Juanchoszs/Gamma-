"""CBOE market refresh use cases (ingestion, metrics, persistence)."""
from __future__ import annotations

import logging
from datetime import datetime

from .. import metrics, store
from ..config import SETTINGS, UNDERLYINGS
from ..ingest import fetch_chain, fetch_index_spot
from ..metrics import ET
from ..state import STATE

log = logging.getLogger(__name__)


def pull_symbol(symbol: str, persist_snapshot: bool) -> None:
    u = UNDERLYINGS[symbol]
    snap = fetch_chain(symbol, u.cboe_symbol)
    enriched = metrics.enrich(snap)
    summary = metrics.summarize(snap, enriched, with_basis=u.future is not None)
    now = datetime.now(ET)

    st = STATE.get(symbol)
    with STATE.lock:
        prev = st.enriched
        prev_feed_ts = st.last_feed_ts

    if (u.role == "target" and prev is not None
            and prev_feed_ts != snap.feed_timestamp):
        flow = metrics.flow_delta(prev, enriched, snap.spot)
        flow["timestamp"] = snap.feed_timestamp
        store.append_daily("flows", symbol, flow, now)

    if persist_snapshot:
        store.save_snapshot(
            symbol, enriched, now,
            source="cboe",
            snapshot_type="LIVE",
            data_quality="VALID",
            market_state="LIVE",
            schema_version=1,
        )
        store.append_history(summary.as_row())

    with STATE.lock:
        st.snapshot = snap
        st.enriched = enriched
        st.summary = summary
        st.last_feed_ts = snap.feed_timestamp
        STATE.last_error = None
    log.info(
        "%s pull ok — spot=%.2f netGEX=%.2f Bn zeroG=%s basis=%s",
        symbol, snap.spot, summary.net_gex / 1e9,
        f"{summary.zero_gamma:.0f}" if summary.zero_gamma else "n/a",
        f"{summary.basis:+.1f}" if summary.basis is not None else "n/a",
    )


def pull_vix() -> None:
    """Fetch the VIX spot used as market context and MCP context."""
    try:
        spot, ts = fetch_index_spot("_VIX")
        store.append_index_spot("vix", {"timestamp": ts, "vix": spot})
    except Exception:  # noqa: BLE001
        log.exception("Échec pull VIX")


def pull_all(force: bool = False) -> None:
    from .. import scheduler as sched

    if SETTINGS.market_hours_only and not sched.market_is_open() and not force:
        return
    persist = sched._CADENCE.tick()
    due = sched._CONSTITUENT_CADENCE.tick()
    persist_constituent = sched._CONSTITUENT_SNAPSHOT.tick()
    if due or force:
        pull_vix()
    for key, u in UNDERLYINGS.items():
        if not u.enabled:
            continue
        if u.role == "context":
            continue
        if u.source == "futopt":
            continue
        is_constituent = u.role == "constituent"
        if is_constituent and not (due or force):
            continue
        try:
            pull_symbol(key, persist_snapshot=(persist_constituent if is_constituent else persist))
        except Exception as e:  # noqa: BLE001
            log.exception("Échec pull %s", key)
            with STATE.lock:
                STATE.last_error = f"{key}: {e}"
