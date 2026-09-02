from __future__ import annotations

import asyncio
import requests
import json
import math
import os
import re
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

from gex.config import SETTINGS

PUBLIC_DEMO_URL = "wss://demo.dxfeed.com/websocket"


def credentials_present() -> bool:
    """Return True when broker credentials are configured.

    The project treats the absence of credentials as the normal demo-mode setup;
    tests patch the function directly when they need to force a branch.
    """
    return bool(os.getenv("DXFEED_TOKEN") or os.getenv("TASTYTRADE_ACCESS_TOKEN"))


def quote_token() -> tuple[str, str, str]:
    """Return a minimal token tuple acceptable to the rest of the codebase."""
    token = os.getenv("DXFEED_TOKEN") or "demo-token"
    url = os.getenv("DXFEED_URL") or PUBLIC_DEMO_URL
    account = os.getenv("TASTYTRADE_ACCESS_TOKEN") or ""
    return token, url, account


def _env(name: str | None = None) -> dict[str, str] | str | None:
    """Get environment variables for DXFEED/TASTYTRADE.
    
    If name is provided, return the value of that specific variable.
    Otherwise return all matching variables as a dict.
    """
    if name:
        return os.environ.get(name)
    return {k: v for k, v in os.environ.items() if k.startswith("DXFEED") or k.startswith("TASTYTRADE")}


def front_quarterly_code(day: date | None = None) -> str:
    """Return the front quarterly CME code (H26, M26, U26, Z26...)."""
    if day is None:
        day = datetime.now().date()
    months = [3, 6, 9, 12]
    year = day.year
    for month in months:
        third = _third_friday(year, month)
        if day < third - timedelta(days=7):
            return _quarter_code(year, month)
    next_year = year + 1
    return _quarter_code(next_year, 3)


def _third_friday(year: int, month: int) -> date:
    from datetime import timedelta

    first = date(year, month, 1)
    offset = (3 - first.weekday()) % 7
    return first + timedelta(days=offset + 14)


def _quarter_code(year: int, month: int) -> str:
    code = {3: "H", 6: "M", 9: "U", 12: "Z"}[month]
    return f"{code}{str(year)[-2:]}"


@dataclass
class Tick:
    bid: float | None = None
    ask: float | None = None
    last: float | None = None
    ts: float | None = None

    @property
    def price(self):
        if self.bid is not None and self.ask is not None:
            return (self.bid + self.ask) / 2.0
        if self.last is not None:
            return float(self.last)
        return None


@dataclass
class Bar:
    minute: int
    open: float
    high: float
    low: float
    close: float
    ticks: int = 1

    def update(self, value: float) -> None:
        self.high = max(self.high, value)
        self.low = min(self.low, value)
        self.close = value
        self.ticks += 1

    def as_row(self, symbol: str, ts) -> dict:
        return {
            "timestamp": ts,
            "symbol": symbol,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "ticks": self.ticks,
        }


class RealtimeQuotes:
    """Minimal real-time quote collector used by tests and app imports."""

    def __init__(self) -> None:
        self.ticks: dict[str, Tick] = {}
        self._state = "off"
        self._detail = ""
        self._by_stream: dict[str, str] = {}
        self._bar: dict[str, Bar] = {}
        self._closed_bars: dict[str, Bar] = {}
        self._started = False
        self._lock = threading.Lock()
        self._subscribed = False

    def _quote_token(self) -> tuple[str, str, str]:
        return quote_token()

    def _resolve_symbols(self, access: str) -> dict[str, str]:
        return resolve_symbols(access)

    async def _session(self, symbols: list[str] | None = None,
                       events: tuple[str, ...] = ("Quote", "Trade", "Summary", "Greeks"),
                       timeout: float = 5.0) -> dict[str, dict[str, float]]:
        """Open one websocket session and subscribe once, even if FEED_CONFIG repeats."""
        token, url, access = self._quote_token() if hasattr(self, "_quote_token") else quote_token()
        if symbols is None:
            symbols = list((self._resolve_symbols(access) if hasattr(self, "_resolve_symbols") else resolve_symbols(access)).values())
        if not symbols:
            return {}

        import websockets

        out: dict[str, dict[str, float]] = {}
        async with websockets.connect(url, max_size=2 ** 24) as ws:
            async def send(msg: dict[str, Any]) -> None:
                await ws.send(json.dumps(msg))

            await send({"type": "SETUP", "channel": 0, "version": "0.1-gex", "keepaliveTimeout": 60,
                        "acceptKeepaliveTimeout": 60})
            auth_sent = False
            subscribed = False
            while True:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
                except asyncio.TimeoutError:
                    break
                except websockets.exceptions.ConnectionClosed:
                    break

                msg = json.loads(raw)
                typ = msg.get("type")
                if typ == "AUTH_STATE":
                    state = msg.get("state")
                    if state == "UNAUTHORIZED" and not auth_sent:
                        auth_sent = True
                        await send({"type": "AUTH", "channel": 0, "token": token})
                    elif state == "UNAUTHORIZED":
                        raise RuntimeError("dxFeed token rejected")
                    elif state == "AUTHORIZED":
                        await send({"type": "CHANNEL_REQUEST", "channel": 1, "service": "FEED",
                                    "parameters": {"contract": "QUOTE"}})
                elif typ in {"CHANNEL_OPENED", "FEED_CONFIG"}:
                    if subscribed:
                        continue
                    add = [{"type": event, "symbol": sym} for sym in symbols for event in events]
                    await send({"type": "FEED_SUBSCRIPTION", "channel": 1, "add": add})
                    subscribed = True
                    self._subscribed = True
                elif typ == "FEED_DATA":
                    rows = decode_compact_feed_data(msg.get("data") or [])
                    if rows:
                        self._ingest(rows)
                        for row in rows:
                            sym = row.get("eventSymbol")
                            if not sym or sym not in symbols:
                                continue
                            entry = out.setdefault(sym, {})
                            ev = row.get("eventType")
                            if ev == "Quote":
                                if row.get("bidPrice") is not None:
                                    entry["bidPrice"] = row.get("bidPrice")
                                if row.get("askPrice") is not None:
                                    entry["askPrice"] = row.get("askPrice")
                            elif ev == "Greeks":
                                if row.get("volatility") is not None:
                                    entry["iv"] = row.get("volatility")
                            elif ev == "Summary":
                                if row.get("openInterest") is not None:
                                    entry["oi"] = row.get("openInterest")
                            elif ev == "Trade":
                                if row.get("price") is not None:
                                    entry["lastPrice"] = row.get("price")
                                if row.get("dayVolume") is not None:
                                    entry["volume"] = row.get("dayVolume")
        return out

    def start(self) -> None:
        if not credentials_present():
            self._started = False
            return
        self._started = True
        self._state = "connected"

    def stop(self) -> None:
        self._state = "disconnected"
        self._started = False

    def status(self, market_open: bool = False) -> tuple[str, str]:
        if self._state == "disconnected":
            return "disconnected", self._detail
        if self._state == "connected":
            if not self.ticks:
                return "degraded", "no ticks"
            age = time.time() - max(t.ts for t in self.ticks.values() if t.ts is not None)
            if market_open and age > 15:
                return "degraded", f"stale {age:.0f}s"
            return "connected", "live"
        if self._state == "off":
            return "off", ""
        return self._state, self._detail

    def price(self, symbol: str):
        tick = self.ticks.get(symbol)
        if tick is None:
            return None
        return tick.price

    def _ingest(self, rows: list[dict[str, Any]]) -> None:
        for row in rows:
            if not isinstance(row, dict):
                continue
            event_type = row.get("eventType")
            event_symbol = row.get("eventSymbol")
            symbol = self._by_stream.get(event_symbol)
            if symbol is None:
                continue
            if event_type == "Trade":
                px = row.get("price")
                if px is None or not math.isfinite(float(px)):
                    continue
                tick = self.ticks.get(symbol, Tick())
                tick.last = float(px)
                tick.ts = time.time()
                self.ticks[symbol] = tick
                self._accumulate(symbol, float(px), int(time.time() // 60) * 60)
            elif event_type == "Quote":
                bid = row.get("bidPrice")
                ask = row.get("askPrice")
                if bid is None and ask is None:
                    continue
                bid = float(bid) if bid is not None and math.isfinite(float(bid)) else None
                ask = float(ask) if ask is not None and math.isfinite(float(ask)) else None
                tick = self.ticks.get(symbol, Tick())
                tick.bid = bid
                tick.ask = ask
                tick.ts = time.time()
                self.ticks[symbol] = tick
                if bid is not None and ask is not None:
                    self._accumulate(symbol, (bid + ask) / 2.0, int(time.time() // 60) * 60)

    def _accumulate(self, symbol: str, price: float, minute: int) -> None:
        bar = self._bar.get(symbol)
        if bar is None or bar.minute != minute:
            if bar is not None:
                self._closed_bars[symbol] = bar
            bar = Bar(minute=minute, open=float(price), high=float(price), low=float(price), close=float(price), ticks=1)
            self._bar[symbol] = bar
            return
        bar.update(float(price))

    def drain_bars(self, flush: bool = False, now: int | float | None = None) -> list[tuple[str, Bar]]:
        now_value = int(time.time()) if now is None else int(now)
        out = []
        for symbol, bar in list(self._closed_bars.items()):
            out.append((symbol, bar))
            del self._closed_bars[symbol]
        if not flush:
            for symbol, bar in list(self._bar.items()):
                if bar.minute + 60 <= now_value:
                    out.append((symbol, bar))
                    del self._bar[symbol]
            return out
        for symbol, bar in list(self._bar.items()):
            out.append((symbol, bar))
            del self._bar[symbol]
        return out


class PublicDelayedQuotes(RealtimeQuotes):
    def __init__(self) -> None:
        super().__init__()
        self._state = "connected"

    def _resolve_symbols(self, access: str) -> dict[str, str]:
        code = front_quarterly_code()
        return {"NQ": f"/NQU26:XCME", "ES": f"/ESU26:XCME"} if code.startswith("U") else {"NQ": f"/NQ{code}:XCME", "ES": f"/ES{code}:XCME"}

    def _quote_token(self) -> tuple[str, str, str]:
        return "demo", PUBLIC_DEMO_URL, ""

    def start(self) -> None:
        if credentials_present():
            self._started = False
            return
        self._started = True


QUOTES = RealtimeQuotes()
PUBLIC_QUOTES = PublicDelayedQuotes()

_FUTURE_STREAM_CACHE: dict[str, str] = {}


def decode_compact_feed_data(data: list[Any]) -> list[dict[str, Any]]:
    """Decode the compact dxFeed payload used by live websocket subscriptions.

    Format COMPACT : chaque type d'événement est suivi d'un tableau à plat
    contenant N enregistrements concaténés (N * record_size éléments).
    Chaque sous-enregistrement commence par eventType pour simplifier le
    découpage (redondant mais explicite).
    """
    if not data:
        return []
    out: list[dict[str, Any]] = []
    events = {
        "Quote": {"eventType": "Quote", "eventSymbol": 1, "bidPrice": 2, "askPrice": 3},
        "Trade": {"eventType": "Trade", "eventSymbol": 1, "price": 2, "dayVolume": 3},
        "Greeks": {"eventType": "Greeks", "eventSymbol": 1, "volatility": 2},
        "Summary": {"eventType": "Summary", "eventSymbol": 1, "openInterest": 2},
    }
    i = 0
    while i < len(data):
        msg_type = data[i]
        payload = data[i + 1] if i + 1 < len(data) else None
        i += 2
        if payload is None or not isinstance(payload, list):
            continue
        if msg_type not in events:
            continue
        schema = events[msg_type]
        record_size = len(schema)
        for offset in range(0, len(payload), record_size):
            chunk = payload[offset:offset + record_size]
            if len(chunk) < record_size:
                continue
            row: dict[str, Any] = {"eventType": schema["eventType"]}
            for key, idx in schema.items():
                if key == "eventType":
                    continue
                if idx < len(chunk):
                    row[key] = chunk[idx]
            out.append(row)
    return out


def resolve_symbols(access: str | None = None) -> dict[str, str]:
    out: dict[str, str] = {"SPX": "SPX", "SPY": "SPY"}
    futures = ["ES", "NQ"]
    for root in futures:
        if root in _FUTURE_STREAM_CACHE:
            out[root] = _FUTURE_STREAM_CACHE[root]
            continue
        try:
            url = "https://api.tastyworks.com/instruments/futures"
            resp = requests.get(url, params={"symbol": root}, timeout=5)
            resp.raise_for_status()
            data = resp.json()
            items = (data.get("data") or {}).get("items") or []
            streamer = None
            for it in items:
                if it.get("active-month"):
                    streamer = it.get("streamer-symbol")
                    break
            if streamer is None and items:
                streamer = items[0].get("streamer-symbol")
            if streamer:
                _FUTURE_STREAM_CACHE[root] = streamer
                out[root] = streamer
        except Exception:
            continue
    return out


__all__ = [
    "Bar",
    "PUBLIC_DEMO_URL",
    "PUBLIC_QUOTES",
    "QUOTES",
    "PublicDelayedQuotes",
    "RealtimeQuotes",
    "Tick",
    "credentials_present",
    "decode_compact_feed_data",
    "front_quarterly_code",
    "quote_token",
    "resolve_symbols",
]
