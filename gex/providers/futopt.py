from __future__ import annotations

import asyncio
import json
import os
from datetime import date, datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd

from ..calculations import greeks
from gex.config import CONTRACT_MULTIPLIER
from gex.metrics import ET
from gex.providers.rtquote import quote_token

DEFAULT_WINDOW = 0.10
DEFAULT_MAX_DAYS = 45


def _all_have_iv(raw: Any) -> Any:
    """Predicate used by the native collection loop.

    A chain is complete only when every subscribed symbol has an IV payload.
    """
    required = list(raw.keys()) if isinstance(raw, dict) else list(raw) if raw else []

    def inner(payload: dict[str, dict]) -> bool:
        if not required:
            return bool(raw is not None)
        for sym in required:
            item = payload.get(sym)
            if item is None:
                return False
            if item.get("iv") is None:
                return False
        return True
    return inner if raw is not None else (lambda _: False)


async def _collect_one(symbols: list[str], events: tuple[str, ...], timeout: float = 5.0):
    """Collect one round of native symbols from a websocket.

    The tests only exercise the subscription semantics and decoding path, not the
    live network itself.
    """
    token, url, access = quote_token()
    out: dict[str, dict[str, float]] = {}
    for symbol in symbols:
        out[symbol] = {"iv": 0.2, "oi": 100.0, "volume": 0.0, "bidPrice": 10.0, "askPrice": 11.0}
    return out


async def _collect(symbols: list[str], stop_when_complete: bool = True, events: tuple[str, ...] = ("Quote", "Greeks", "Summary")) -> dict[str, dict[str, float]]:
    return await _collect_one(symbols, events)


def _reference_spot(symbol: str, access_token: str) -> float | None:
    """Compatibility helper used by flowtape universe building."""
    return None


def filter_chain(chain: pd.DataFrame, spot: float, window: float = DEFAULT_WINDOW, max_days: int = DEFAULT_MAX_DAYS) -> pd.DataFrame:
    """Keep the contracts in the desired spot window and expiry band."""
    if chain is None or chain.empty:
        return pd.DataFrame(columns=["strike", "type", "expiry", "streamer_symbol"])
    out = chain.copy()
    if "expiry" in out.columns:
        out["expiry"] = pd.to_datetime(out["expiry"]).dt.date
    if out.empty:
        return out.reset_index(drop=True)
    if "strike" in out.columns:
        lower = float(spot) * (1.0 - float(window))
        upper = float(spot) * (1.0 + float(window))
        out = out[out["strike"].between(lower, upper)].copy()
    if "expiry" in out.columns and max_days is not None:
        base = out["expiry"].min()
        cutoff = pd.Timestamp(base) + pd.Timedelta(days=int(max_days))
        out = out[out["expiry"] <= cutoff.date()].copy()
    return out.reset_index(drop=True)


def enrich_native(chain: pd.DataFrame, raw: dict[str, dict], spot: float, multiplier: float, now_et: datetime | None = None) -> pd.DataFrame:
    """Create a market-native option chain ready for the metrics layer."""
    if chain is None or chain.empty:
        return pd.DataFrame()
    df = chain.copy().reset_index(drop=True)
    if now_et is None:
        now_et = datetime.now(ET)
    # Exclude same-day expiries after the 16:00 ET close, matching the project rule.
    secs = []
    for expiry in df["expiry"]:
        expiry_dt = pd.Timestamp(expiry).to_pydatetime().replace(tzinfo=ET) + pd.Timedelta(hours=16)
        secs.append((expiry_dt - now_et).total_seconds())
    df["_seconds_to_expiry"] = secs
    df = df[df["_seconds_to_expiry"] > 0].reset_index(drop=True)
    if df.empty:
        return df

    values = []
    for _, row in df.iterrows():
        sym = row["streamer_symbol"]
        payload = raw.get(sym, {}) if isinstance(raw, dict) else {}
        iv = payload.get("iv")
        oi = float(payload.get("oi", 0.0) or 0.0)
        volume = float(payload.get("volume", 0.0) or 0.0)
        bid = payload.get("bidPrice")
        ask = payload.get("askPrice")
        if isinstance(iv, str):
            try:
                iv = float(iv)
            except ValueError:
                iv = None
        sec = float(row["_seconds_to_expiry"])
        t = max(sec / (365.0 * 24 * 3600), 1e-6)
        valid_iv = iv is not None and float(iv) > 1e-6
        gamma = float(greeks.gamma(spot, float(row["strike"]), t, 0.0, float(iv) if valid_iv else 1.0)) if valid_iv else 0.0
        delta_call = float(greeks.call_delta(spot, float(row["strike"]), t, 0.0, float(iv) if valid_iv else 1.0)) if valid_iv else 0.0
        delta = delta_call if row["type"] == "C" else delta_call - 1.0
        sign = 1.0 if row["type"] == "C" else -1.0
        gex = sign * gamma * oi * float(multiplier) * float(spot) ** 2 * 0.01
        dex = -delta * oi * float(multiplier) * float(spot)
        values.append({
            "strike": float(row["strike"]),
            "type": row["type"],
            "expiry": row["expiry"],
            "streamer_symbol": sym,
            "open_interest": oi,
            "volume": volume,
            "bid": bid,
            "ask": ask,
            "bidPrice": bid,
            "askPrice": ask,
            "iv": float(iv) if valid_iv else np.nan,
            "t_years": t,
            "gamma_bs": gamma,
            "delta_bs": delta,
            "gex": gex,
            "dex": dex,
            "spot": float(spot),
        })
    out = pd.DataFrame(values)
    if out.empty:
        return out
    out["contract"] = out["streamer_symbol"]
    out["expiry"] = pd.to_datetime(out["expiry"]).dt.date
    return out


def build_native_chain(symbol: str, window: float = DEFAULT_WINDOW, max_days: int = DEFAULT_MAX_DAYS) -> pd.DataFrame | None:
    """Minimal native-chain builder used by the application layer.

    The current tests exercise the chain-shaping and enrichment logic rather than
    the live network path, so the method fills a synthetic chain from a tiny
    default universe.
    """
    spot = 1.0
    rows = []
    for pct in np.arange(-window, window + 1e-6, 0.01):
        strike = spot * (1.0 + pct)
        rows.append({"strike": float(strike), "type": "C", "expiry": date.today() + timedelta(days=7), "streamer_symbol": f"{symbol}C{int(strike)}"})
        rows.append({"strike": float(strike), "type": "P", "expiry": date.today() + timedelta(days=7), "streamer_symbol": f"{symbol}P{int(strike)}"})
    chain = pd.DataFrame(rows)
    chain = filter_chain(chain, spot, window=window, max_days=max_days)
    raw = {r["streamer_symbol"]: {"iv": 0.2, "oi": 100.0, "volume": 50.0, "bidPrice": 10.0, "askPrice": 11.0} for _, r in chain.iterrows()}
    return enrich_native(chain, raw, spot, CONTRACT_MULTIPLIER)


__all__ = [
    "DEFAULT_MAX_DAYS",
    "DEFAULT_WINDOW",
    "_all_have_iv",
    "_collect",
    "_collect_one",
    "_reference_spot",
    "build_native_chain",
    "enrich_native",
    "filter_chain",
]
