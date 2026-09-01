"""Volume-based contract rolls for continuous NQ/ES series."""
from __future__ import annotations

import json
import logging
import threading
from datetime import date, timedelta
from pathlib import Path

import requests

from ..config import SETTINGS

log = logging.getLogger(__name__)

FUTURES_URL = "https://api.tastyworks.com/instruments/futures"

# Keep a short history so roll decisions remain auditable.
KEEP_SESSIONS = 15

_LOCK = threading.Lock()


def _state_path() -> Path:
    return SETTINGS.data_dir / "ticks" / "_roll_state.json"


def load_state() -> dict:
    p = _state_path()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 — an unreadable state must not block anything
        log.exception("Roll state unreadable — starting fresh")
        return {}


def save_state(state: dict) -> None:
    p = _state_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=1, sort_keys=True), encoding="utf-8")
    tmp.replace(p)


def resolve_pair(code: str, access: str) -> list[tuple[str, str]]:
    """Return streamer and contract symbols for the active and next contracts."""
    r = requests.get(FUTURES_URL, params={"product-code": code},
                     headers={"Authorization": f"Bearer {access}"}, timeout=30)
    r.raise_for_status()
    items = r.json()["data"]["items"]
    out: list[tuple[str, str]] = []
    for flag in ("active-month", "next-active-month"):
        for i in items:
            if i.get(flag) and i.get("streamer-symbol"):
                out.append((i["streamer-symbol"], i.get("symbol") or i["streamer-symbol"]))
                break
    return out


def record_volumes(symbol: str, session: str, per_contract: dict[str, float]) -> None:
    """Accumulate per-contract volume for a session."""
    if not per_contract:
        return
    with _LOCK:
        state = load_state()
        sess = state.setdefault(symbol, {}).setdefault(session, {})
        for contract, vol in per_contract.items():
            sess[contract] = sess.get(contract, 0) + float(vol)
        # Retain only the most recent sessions.
        keep = dict(sorted(state[symbol].items())[-KEEP_SESSIONS:])
        state[symbol] = keep
        save_state(state)


def dominant(symbol: str, session: str, contracts: list[str],
             state: dict | None = None) -> str | None:
    """Return the contract with the highest volume in the previous session."""
    if not contracts:
        return None
    state = load_state() if state is None else state
    hist = (state.get(symbol) or {})
    # Search strictly earlier sessions, newest first.
    for prev in sorted((s for s in hist if s < session), reverse=True):
        vols = {c: hist[prev].get(c, 0) for c in contracts}
        if any(vols.values()):
            best = max(vols, key=lambda c: vols[c])
            if best != contracts[0]:
                log.info("Roll %s: session %s written on %s (volume %s = %s vs %s = %s)",
                         symbol, session, best, best, vols[best],
                         contracts[0], vols[contracts[0]])
            return best
    return contracts[0]


def previous_session(session: str) -> str:
    """Return the previous weekday session."""
    d = date.fromisoformat(session) - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d.isoformat()
