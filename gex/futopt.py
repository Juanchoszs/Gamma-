"""Native CME futures-option ingestion for NQ and ES.

Futures options have a distinct gamma structure. Multipliers are $20/point for
NQ and $50/point for ES, not 100 for cash-index options. The subscription
window avoids collecting all roughly 7,000 NQ contracts; bursts are capped at
6,000 because larger requests can be rejected. Gamma is recomputed locally
with Black–Scholes while dxFeed supplies IV, keeping history consistent.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime

import numpy as np
import pandas as pd
import requests

from . import greeks, store
from . import rates
from .metrics import ET, YEAR_SECONDS, seconds_to_expiry
from .rtquote import QUOTES, decode_compact_feed_data, feed_setup_message, quote_token

log = logging.getLogger(__name__)

FUTURES_URL = "https://api.tastyworks.com/instruments/futures"
CHAIN_URL = "https://api.tastyworks.com/futures-option-chains/{code}"







IDLE_TIMEOUT_S = 20.0






DEFAULT_WINDOW = 0.08
DEFAULT_MAX_DAYS = 14










MAX_BURST = 6000  




MAX_DURATION_S = 90.0








COMPLETION_GRACE_S = 5.0

_multiplier_cache: dict[str, float] = {}


def get_multiplier(product_code: str, access_token: str) -> float | None:
    """Return and cache the futures dollar-per-point multiplier."""
    if product_code in _multiplier_cache:
        return _multiplier_cache[product_code]
    r = requests.get(FUTURES_URL, params={"product-code": product_code},
                     headers={"Authorization": f"Bearer {access_token}"}, timeout=30)
    r.raise_for_status()
    items = [i for i in r.json()["data"]["items"] if i.get("active-month")]
    if not items:
        return None
    mult = float(items[0]["notional-multiplier"])
    _multiplier_cache[product_code] = mult
    return mult


def fetch_chain_instruments(product_code: str, access_token: str) -> pd.DataFrame:
    """Return one reference row per contract; market data arrives via dxLink."""
    r = requests.get(CHAIN_URL.format(code=product_code),
                     headers={"Authorization": f"Bearer {access_token}"}, timeout=90)
    r.raise_for_status()
    items = r.json()["data"]["items"]
    rows = [{
        "strike": float(i["strike-price"]),
        "type": i["option-type"],
        "expiry": pd.Timestamp(i["expiration-date"]).date(),
        "streamer_symbol": i["streamer-symbol"],
        "underlying_symbol": i.get("underlying-symbol"),
    } for i in items if i.get("streamer-symbol")]
    return pd.DataFrame(rows)


def filter_chain(chain: pd.DataFrame, spot: float, window: float = DEFAULT_WINDOW,
                 max_days: int = DEFAULT_MAX_DAYS) -> pd.DataFrame:
    """Keep relevant strikes and expiries to control subscription volume."""
    if chain.empty:
        return chain
    lo, hi = spot * (1 - window), spot * (1 + window)
    horizon = (pd.Timestamp.now(tz=ET).date()
               + pd.Timedelta(days=max_days))
    return chain[chain["strike"].between(lo, hi)
                & (chain["expiry"] <= horizon)].reset_index(drop=True)


async def _collect_one(streamer_symbols: list[str],
                       events: tuple[str, ...],
                       timeout: float,
                       early_stop=None,
                       grace_s: float = 0.0) -> dict[str, dict]:
    """Collect one subscription burst on a single connection.

    The full burst must be one message because later bursts on the same
    connection can be acknowledged without returning snapshot data. Early
    stopping avoids the 90-second ceiling for continuously quoted futures.
    ``grace_s`` drains slower Summary/open-interest events after IV arrives;
    on SPX, omitting the grace period lost about 6.5% of OI (roughly $1B of
    net GEX) versus CBOE.
    """
    import time as _time

    import websockets

    token, url, _ = quote_token()
    out: dict[str, dict] = {}

    
    
    
    async with websockets.connect(url, max_size=2 ** 24, ping_interval=None) as ws:
        async def send(m):
            await ws.send(json.dumps(m))

        await send({"type": "SETUP", "channel": 0, "version": "0.1-futopt",
                    "keepaliveTimeout": 60, "acceptKeepaliveTimeout": 60})
        auth_sent = False
        
        
        
        
        
        
        subscribed = False
        
        
        
        
        
        
        started = last_data = _time.monotonic()
        
        
        
        stop_deadline: float | None = None
        while True:
            now = _time.monotonic()
            remaining = min(timeout - (now - last_data),
                            MAX_DURATION_S - (now - started))
            if stop_deadline is not None:
                remaining = min(remaining, stop_deadline - now)
            if remaining <= 0:
                break
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=remaining)
            except asyncio.TimeoutError:
                break
            except websockets.exceptions.ConnectionClosed:
                
                break
            m = json.loads(raw)
            typ = m.get("type")
            if typ == "AUTH_STATE":
                state = m.get("state")
                if state == "UNAUTHORIZED" and not auth_sent:
                    auth_sent = True
                    await send({"type": "AUTH", "channel": 0, "token": token})
                elif state == "UNAUTHORIZED":
                    raise RuntimeError("jeton dxFeed refusé")
                elif state == "AUTHORIZED":
                    await send({"type": "CHANNEL_REQUEST", "channel": 1,
                                "service": "FEED",
                                "parameters": {"contract": "AUTO"}})
            elif typ == "CHANNEL_OPENED":
                await send(feed_setup_message(1))
            elif typ == "FEED_CONFIG" and not subscribed:
                subscribed = True
                subs = [{"type": e, "symbol": s}
                       for s in streamer_symbols for e in events]
                await send({"type": "FEED_SUBSCRIPTION", "channel": 1, "add": subs})
            elif typ == "KEEPALIVE":
                await send({"type": "KEEPALIVE", "channel": 0})
            elif typ == "ERROR":
                log.warning("dxFeed ERROR pendant la collecte : %s", str(m)[:300])
            elif typ == "FEED_DATA":
                last_data = _time.monotonic()
                for item in decode_compact_feed_data(m.get("data") or []):
                    if not isinstance(item, dict):
                        continue
                    sym = item.get("eventSymbol")
                    if sym not in streamer_symbols:
                        continue
                    d = out.setdefault(sym, {})
                    etype = item.get("eventType")
                    if etype == "Quote":
                        for k in ("bidPrice", "askPrice"):
                            v = item.get(k)
                            if isinstance(v, (int, float)) and v == v:
                                d[k] = float(v)
                    elif etype == "Greeks":
                        v = item.get("volatility")
                        if isinstance(v, (int, float)) and v == v:
                            d["iv"] = float(v)
                    elif etype == "Trade":
                        
                        
                        v = item.get("dayVolume")
                        if isinstance(v, (int, float)) and v == v:
                            d["volume"] = float(v)
                    elif etype == "Summary":
                        v = item.get("openInterest")
                        if isinstance(v, (int, float)) and v == v:
                            d["oi"] = float(v)
                if (early_stop is not None and stop_deadline is None
                        and early_stop(out)):
                    if grace_s <= 0:
                        return out
                    stop_deadline = _time.monotonic() + grace_s
    return out


def _all_have_iv(symbols: list[str]):
    """Build a stop condition that fires after every symbol has IV."""
    total = len(symbols)

    def check(out: dict) -> bool:
        return sum(1 for v in out.values() if "iv" in v) >= total

    return check


async def _collect(streamer_symbols: list[str],
                   events: tuple[str, ...] = ("Quote", "Trade", "Greeks", "Summary"),
                   timeout: float = IDLE_TIMEOUT_S,
                   early_stop=None,
                   stop_when_complete: bool = False,
                   grace_s: float = COMPLETION_GRACE_S) -> dict[str, dict]:
    """Collect and merge events, using sequential connections when necessary.

    ``stop_when_complete`` avoids repeated 90-second waits; a SPX collection
    otherwise took 278 seconds despite data being complete much earlier.
    Completion is evaluated per batch, not against symbols in other batches.
    """
    per_symbol = max(len(events), 1)
    batch_size = max(MAX_BURST // per_symbol, 1)
    out: dict[str, dict] = {}
    for i in range(0, len(streamer_symbols), batch_size):
        batch = streamer_symbols[i:i + batch_size]
        if early_stop is not None:
            
            
            stop, grace = early_stop, 0.0
        elif stop_when_complete:
            stop, grace = _all_have_iv(batch), grace_s
        else:
            stop, grace = None, 0.0
        out.update(await _collect_one(batch, events, timeout,
                                      early_stop=stop, grace_s=grace))
    return out


def enrich_native(chain: pd.DataFrame, raw: dict[str, dict], spot: float,
                  multiplier: float, now_et: datetime | None = None) -> pd.DataFrame:
    """Merge reference and market data and compute gamma, delta, GEX, and DEX."""
    now_et = now_et or datetime.now(ET)
    df = chain.copy()
    md = pd.DataFrame.from_dict(raw, orient="index")
    df = df.merge(md, left_on="streamer_symbol", right_index=True, how="left")
    for col in ("iv", "oi", "volume", "bidPrice", "askPrice"):
        if col not in df.columns:
            df[col] = np.nan
    df = df.rename(columns={"oi": "open_interest", "bidPrice": "bid", "askPrice": "ask"})
    df["open_interest"] = df["open_interest"].fillna(0.0)
    df["volume"] = df["volume"].fillna(0.0)
    df["bid"] = df["bid"].fillna(0.0)
    df["ask"] = df["ask"].fillna(0.0)

    secs = seconds_to_expiry(pd.Series(df["expiry"]), now_et)
    df = df[secs > 0].reset_index(drop=True)
    secs = secs[secs > 0]
    t = np.maximum(secs, 300.0) / YEAR_SECONDS
    df["t_years"] = t

    valid = df["iv"].to_numpy() > 1e-4
    iv = np.where(valid, df["iv"].to_numpy(), 1.0)
    is_call = (df["type"] == "C").to_numpy()
    r = rates.current_rate()
    g = np.where(valid, greeks.gamma(spot, df["strike"].to_numpy(), t, r, iv), 0.0)
    dcall = greeks.call_delta(spot, df["strike"].to_numpy(), t, r, iv)
    d = np.where(valid, np.where(is_call, dcall, dcall - 1.0), np.nan)

    df["gamma_bs"] = g
    df["delta_bs"] = d
    sign = np.where(is_call, 1.0, -1.0)
    oi = df["open_interest"].to_numpy()
    df["gex"] = sign * g * oi * multiplier * spot ** 2 * 0.01
    
    
    
    
    
    
    
    
    df["dex"] = -1.0 * d * oi * multiplier * spot
    df["spot"] = float(spot)
    return df


def _reference_spot(product_code: str, access_token: str) -> float | None:
    """Return the active-future spot from live data or a one-shot quote."""
    live = QUOTES.price(product_code)
    if live:
        return live
    r = requests.get(FUTURES_URL, params={"product-code": product_code},
                     headers={"Authorization": f"Bearer {access_token}"}, timeout=30)
    r.raise_for_status()
    items = [i for i in r.json()["data"]["items"] if i.get("active-month")]
    if not items:
        return None
    stream_sym = items[0]["streamer-symbol"]
    
    
    
    
    def _has_quote(out: dict) -> bool:
        d = out.get(stream_sym, {})
        return d.get("bidPrice") is not None and d.get("askPrice") is not None
    data = asyncio.run(_collect([stream_sym], events=("Quote",), early_stop=_has_quote))
    d = data.get(stream_sym, {})
    bid, ask = d.get("bidPrice"), d.get("askPrice")
    if bid and ask:
        return (bid + ask) / 2
    return None


def build_native_chain(product_code: str, window: float = DEFAULT_WINDOW,
                       max_days: int = DEFAULT_MAX_DAYS) -> pd.DataFrame | None:
    """Build a complete native chain ready for the ``metrics`` functions."""
    _, _, access = quote_token()
    spot = _reference_spot(product_code, access)
    if not spot:
        log.warning("%s : spot indisponible, chaîne native abandonnée", product_code)
        return None
    multiplier = get_multiplier(product_code, access)
    if not multiplier:
        log.warning("%s : multiplicateur indisponible", product_code)
        return None

    chain = fetch_chain_instruments(product_code, access)
    chain = filter_chain(chain, spot, window, max_days)
    if chain.empty:
        log.warning("%s : aucun contrat dans la fenêtre", product_code)
        return None

    raw = asyncio.run(_collect(chain["streamer_symbol"].tolist(),
                               stop_when_complete=True))
    df = enrich_native(chain, raw, spot, multiplier)
    log.info("%s : chaîne native — %d contrats, spot %.2f, multiplicateur %.0f",
             product_code, len(df), spot, multiplier)
    return df


def pull_native(product_code: str, persist: bool = True) -> pd.DataFrame | None:
    """Build and optionally persist a native chain; never raises to the scheduler."""
    try:
        df = build_native_chain(product_code)
    except Exception:  
        log.exception("%s : échec de la chaîne native", product_code)
        return None
    if df is None or df.empty:
        return None
    if persist:
        
        
        
        try:
            store.save_snapshot(
                f"{product_code}_OPT", df, datetime.now(ET),
                source="dxfeed",
                snapshot_type="LIVE",
                data_quality="VALID",
                market_state="LIVE",
                schema_version=1,
            )
        except Exception:  
            log.exception("%s : échec d'écriture du snapshot natif", product_code)
    return df
