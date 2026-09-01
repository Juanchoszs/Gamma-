"""Native index and ETF option chains from dxFeed.

The nested endpoint preserves distinct roots such as weekly and monthly SPX.
In validation, dxFeed supplied open interest for all 178 sampled 0DTE
contracts with zero difference from CBOE, without its roughly 15-minute delay.
"""
from __future__ import annotations

import asyncio
import logging

import pandas as pd
import requests

from . import ingest
from ..config import CONTRACT_MULTIPLIER, UNDERLYINGS
from gex.providers.futopt import DEFAULT_MAX_DAYS, DEFAULT_WINDOW, _collect, enrich_native, filter_chain
from gex.providers.rtquote import QUOTES, quote_token

log = logging.getLogger(__name__)

CHAIN_URL = "https://api.tastyworks.com/option-chains/{symbol}/nested"



NATIVE_INDEX = ("SPX", "NDX", "SPY", "QQQ")


def fetch_chain_instruments(symbol: str, access_token: str) -> pd.DataFrame:
    """Flatten the nested index-option chain into contract reference rows.

    Keep both roots when present (for example, weekly and monthly SPX): they
    are distinct series with separate open interest, and deduplicating them
    would distort GEX by strike.
    """
    r = requests.get(CHAIN_URL.format(symbol=symbol),
                     headers={"Authorization": f"Bearer {access_token}"}, timeout=90)
    r.raise_for_status()
    rows = []
    for item in r.json()["data"]["items"]:
        root = item.get("root-symbol")
        for exp in item.get("expirations", []):
            expiry = pd.Timestamp(exp["expiration-date"]).date()
            for st in exp.get("strikes", []):
                strike = float(st["strike-price"])
                for cp, key in (("C", "call-streamer-symbol"),
                                ("P", "put-streamer-symbol")):
                    stream = st.get(key)
                    if stream:
                        rows.append({"strike": strike, "type": cp, "expiry": expiry,
                                     "streamer_symbol": stream,
                                     "underlying_symbol": root})
    return pd.DataFrame(rows)


def reference_spot(symbol: str) -> float | None:
    """Return the live index spot, falling back to delayed CBOE at startup."""
    live = QUOTES.price(symbol)
    if live:
        return float(live)
    u = UNDERLYINGS.get(symbol)
    if u is None:
        return None
    try:
        spot, _ = ingest.fetch_index_spot(u.cboe_symbol)
        log.info("%s : spot temps réel indisponible, repli sur le spot CBOE", symbol)
        return float(spot)
    except Exception:
        log.exception("%s : spot indisponible", symbol)
        return None


def build_native_chain(symbol: str, window: float = DEFAULT_WINDOW,
                       max_days: int = DEFAULT_MAX_DAYS) -> pd.DataFrame | None:
    """Build a complete native index chain ready for the ``metrics`` functions."""
    _, _, access = quote_token()
    spot = reference_spot(symbol)
    if not spot:
        log.warning("%s : spot indisponible, chaîne native abandonnée", symbol)
        return None

    chain = fetch_chain_instruments(symbol, access)
    chain = filter_chain(chain, spot, window, max_days)
    if chain.empty:
        log.warning("%s : aucun contrat dans la fenêtre", symbol)
        return None

    raw = asyncio.run(_collect(chain["streamer_symbol"].tolist(),
                               stop_when_complete=True))

    df = enrich_native(chain, raw, spot, CONTRACT_MULTIPLIER)
    log.info("%s : chaîne d'indice native — %d contrats, spot %.2f",
             symbol, len(df), spot)
    return df
