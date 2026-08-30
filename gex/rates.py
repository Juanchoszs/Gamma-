"""Load and cache the risk-free rate used by Black-Scholes calculations."""
from __future__ import annotations

import logging
import threading
from datetime import date

import requests

from .config import RISK_FREE_RATE

log = logging.getLogger(__name__)

# Overnight SOFR is a suitable short-term approximation for these option maturities.
SOFR_URL = "https://markets.newyorkfed.org/api/rates/secured/sofr/last/1.json"

_lock = threading.Lock()
_rate: float = RISK_FREE_RATE     # repli tant qu'aucun refresh n'a abouti
_day: date | None = None


def current_rate() -> float:
    """Return the cached rate without making a network request."""
    return _rate


def refresh(force: bool = False) -> float:
    """Fetch and cache the current SOFR value."""
    global _rate, _day
    today = date.today()
    if not force and _day == today:
        return _rate
    try:
        resp = requests.get(SOFR_URL, timeout=15)
        resp.raise_for_status()
        item = resp.json()["refRates"][0]
        rate = float(item["percentRate"]) / 100.0
        # Reject implausible responses rather than contaminating calculated levels.
        if not 0.0 <= rate <= 0.20:
            raise ValueError(f"SOFR hors plage : {item.get('percentRate')}")
        with _lock:
            _rate, _day = rate, today
        log.info("Taux sans risque r = %.4f (SOFR effectif %s)",
                 rate, item.get("effectiveDate"))
    except Exception:  # noqa: BLE001 - preserve the last usable rate
        log.warning("SOFR indisponible, repli sur r = %.4f", _rate)
    return _rate
