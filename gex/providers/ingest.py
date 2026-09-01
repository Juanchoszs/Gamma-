"""Ingestion of option chains from CBOE delayed endpoint.

Undocumented public endpoint: https://cdn.cboe.com/api/global/
delayed_quotes/options/{symbol}.json (indices prefixed with "_").
A GET returns the full chain (bid/ask, IV, OI, volume, CBOE Greeks)
plus the spot. Delay ~15 min at source.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, date, timezone
from zoneinfo import ZoneInfo

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from gex.domain import DataQuality
from gex.domain.models import ChainSnapshot

_ET = ZoneInfo("America/New_York")

log = logging.getLogger(__name__)

BASE_URL = "https://cdn.cboe.com/api/global/delayed_quotes/options/{sym}.json"

# OCC symbol: ROOT + YYMMDD + C/P + strike*1000 in 8 digits.
OCC_RE = re.compile(r"^(?P<root>.+?)(?P<exp>\d{6})(?P<cp>[CP])(?P<strike>\d{8})$")


def _session() -> requests.Session:
    retry = Retry(
        total=4,
        backoff_factor=2.0,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
    )
    s = requests.Session()
    s.mount("https://", HTTPAdapter(max_retries=retry))
    s.headers["User-Agent"] = "gex-dashboard/0.1 (personal analytics)"
    return s


_SESSION = _session()


def parse_occ(symbol: str) -> tuple[date, str, float] | None:
    m = OCC_RE.match(symbol)
    if not m:
        return None
    exp = datetime.strptime(m.group("exp"), "%y%m%d").date()
    return exp, m.group("cp"), int(m.group("strike")) / 1000.0


def parse_chain(symbol: str, raw: dict, fetched_at: datetime) -> ChainSnapshot:
    data = raw["data"]
    rows = []
    for o in data.get("options", []):
        parsed = parse_occ(o["option"])
        if parsed is None:
            log.warning("Symbole OCC non reconnu: %s", o["option"])
            continue
        exp, cp, strike = parsed
        rows.append(
            {
                "contract": o["option"],
                "expiry": exp,
                "type": cp,
                "strike": strike,
                "bid": o.get("bid", 0.0),
                "ask": o.get("ask", 0.0),
                "iv": o.get("iv", 0.0),
                "open_interest": o.get("open_interest", 0.0),
                "volume": o.get("volume", 0.0),
                "delta_cboe": o.get("delta", 0.0),
                "gamma_cboe": o.get("gamma", 0.0),
                "last_trade_price": o.get("last_trade_price", 0.0),
            }
        )
    df = pd.DataFrame(rows)
    return ChainSnapshot(
        symbol=symbol,
        spot=float(data["current_price"]),
        feed_timestamp=datetime.strptime(raw["timestamp"], "%Y-%m-%d %H:%M:%S")
        .replace(tzinfo=timezone.utc)
        .astimezone(_ET)
        .replace(tzinfo=None),
        fetched_at=fetched_at,
        options=df,
    )


def fetch_chain(symbol: str, cboe_symbol: str, timeout: int = 60) -> ChainSnapshot:
    """Pull une chaîne complète. Lève requests.HTTPError après épuisement des retries."""
    url = BASE_URL.format(sym=cboe_symbol)
    resp = _SESSION.get(url, timeout=timeout)
    resp.raise_for_status()
    return parse_chain(symbol, resp.json(), fetched_at=datetime.utcnow())


def fetch_index_spot(cboe_symbol: str, timeout: int = 30) -> tuple[float, datetime]:
    """Pull léger : juste le spot d'un indice (ex. VIX en confluence pour
    get_market_context), sans parser sa chaîne d'options — même endpoint que
    fetch_chain, qui expose `current_price` quel que soit le symbole."""
    url = BASE_URL.format(sym=cboe_symbol)
    resp = _SESSION.get(url, timeout=timeout)
    resp.raise_for_status()
    raw = resp.json()
    ts = (
        datetime.strptime(raw["timestamp"], "%Y-%m-%d %H:%M:%S")
        .replace(tzinfo=timezone.utc)
        .astimezone(_ET)
        .replace(tzinfo=None)
    )
    return float(raw["data"]["current_price"]), ts


__all__ = ["_ET", "ChainSnapshot", "fetch_chain", "fetch_index_spot", "parse_occ"]
