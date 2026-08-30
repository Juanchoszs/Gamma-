"""Optional underlying quotes via dxFeed/dxLink.

The dashboard remains functional with CBOE chains delayed about 15 minutes.
Broker data is display-only and is not persisted to shareable Parquet files.
COMPACT feed decoding keeps the downstream event shape stable; daily volume
comes from ``Trade.dayVolume`` while open interest comes from ``Summary``.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import date, timedelta

import requests

from .config import UNDERLYINGS

log = logging.getLogger(__name__)

TOKEN_URL = "https://api.tastyworks.com/oauth/token"
QUOTE_TOKEN_URL = "https://api.tastyworks.com/api-quote-tokens"
FUTURES_URL = "https://api.tastyworks.com/instruments/futures"






PUBLIC_DEMO_URL = "wss://demo.dxfeed.com/market-data/dxlink-ws"

_QUARTERLY_MONTHS = (3, 6, 9, 12)
_QUARTERLY_CODE = {3: "H", 6: "M", 9: "U", 12: "Z"}


def _third_friday(year: int, month: int) -> date:
    d = date(year, month, 1)
    first_friday = 1 + (4 - d.weekday()) % 7
    return date(year, month, first_friday + 14)


def front_quarterly_code(today: date | None = None) -> str:
    """Return the active quarterly futures code without a network request.

    Roll to the next contract about one week before the third Friday. This
    approximation is sufficient for display quotes, not for trading the roll.
    """
    today = today or date.today()
    for month in _QUARTERLY_MONTHS:
        expiry = _third_friday(today.year, month)
        if today <= expiry - timedelta(days=7):
            return f"{_QUARTERLY_CODE[month]}{today.year % 100:02d}"
    year = today.year + 1
    return f"{_QUARTERLY_CODE[3]}{year % 100:02d}"




STALE_S = 30.0

BACKOFF_START, BACKOFF_MAX = 2.0, 60.0


def _env(name: str) -> str | None:
    """Read an environment variable, falling back to the Windows user registry."""
    val = os.environ.get(name)
    if not val and sys.platform == "win32":
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
                val = winreg.QueryValueEx(k, name)[0]
        except OSError:
            pass
    return val


def credentials_present() -> bool:
    return all(_env(n) for n in
               ("TT_REFRESH", "TASTYTRADE_CLIENT_ID", "TASTYTRADE_CLIENT_SECRET"))


















COMPACT_FIELDS: dict[str, list[str]] = {
    "Quote": ["eventType", "eventSymbol", "bidPrice", "askPrice"],
    "Trade": ["eventType", "eventSymbol", "price", "dayVolume"],
    "Greeks": ["eventType", "eventSymbol", "volatility"],
    "Summary": ["eventType", "eventSymbol", "openInterest"],
}


def decode_compact_feed_data(data: list) -> list[dict]:
    """Decode COMPACT FEED_DATA into the dict form used by downstream code.

    Data alternates ``[typeTag, flat_values, ...]``. Values repeat the fields
    declared in ``FEED_SETUP`` positionally; unknown tags are ignored.
    """
    out: list[dict] = []
    i = 0
    while i + 1 < len(data):
        type_tag, flat = data[i], data[i + 1]
        i += 2
        fields = COMPACT_FIELDS.get(type_tag)
        if not fields or not isinstance(flat, list):
            continue
        n = len(fields)
        for j in range(0, len(flat) - n + 1, n):
            out.append(dict(zip(fields, flat[j:j + n])))
    return out


def feed_setup_message(channel: int) -> dict:
    """Build the shared FEED_SETUP frame for the quote collectors."""
    return {"type": "FEED_SETUP", "channel": channel,
            "acceptAggregationPeriod": 10, "acceptDataFormat": "COMPACT",
            "acceptEventFields": COMPACT_FIELDS}


def quote_token() -> tuple[str, str, str]:
    """Return the dxFeed token, dxLink URL, and tastytrade access token."""
    r = requests.post(TOKEN_URL, data={
        "grant_type": "refresh_token",
        "refresh_token": _env("TT_REFRESH"),
        "client_id": _env("TASTYTRADE_CLIENT_ID"),
        "client_secret": _env("TASTYTRADE_CLIENT_SECRET"),
    }, timeout=30)
    r.raise_for_status()
    access = r.json()["access_token"]
    q = requests.get(QUOTE_TOKEN_URL,
                     headers={"Authorization": f"Bearer {access}"}, timeout=30)
    q.raise_for_status()
    d = q.json()["data"]
    return d["token"], d["dxlink-url"], access


def _is_future_key(key: str) -> bool:
    """Return whether a key identifies a future rather than an index or stock."""
    u = UNDERLYINGS.get(key)
    return u is not None and u.source == "futopt"






_FUTURE_STREAM_CACHE: dict[str, str] = {}


def resolve_symbols(access: str) -> dict[str, str]:
    """Map internal keys to dxFeed symbols.

    Indices, ETFs, and stocks use their tickers. Futures require the active
    contract from the API; unresolved futures are omitted rather than falling
    back to the raw code, because ``ES`` and ``NQ`` can name unrelated stocks.
    """
    out = {u.key: u.key for u in UNDERLYINGS.values()
           if u.enabled and not _is_future_key(u.key)}
    h = {"Authorization": f"Bearer {access}"}
    for code in {u.future for u in UNDERLYINGS.values() if u.future and u.enabled}:
        cached = _FUTURE_STREAM_CACHE.get(code)
        if cached:
            out[code] = cached
            continue
        try:
            r = requests.get(FUTURES_URL, params={"product-code": code},
                             headers=h, timeout=30)
            r.raise_for_status()
            items = [i for i in r.json()["data"]["items"] if i.get("active-month")]
            if items:
                out[code] = _FUTURE_STREAM_CACHE[code] = items[0]["streamer-symbol"]
            else:
                log.warning("Aucun contrat actif pour %s — %s exclu du flux", code, code)
        except Exception as exc:
            log.warning("Symbole future %s non résolu (%s) — exclu du flux "
                        "plutôt que rabattu sur le ticker action homonyme",
                        code, exc)
    return out


@dataclass
class Tick:
    bid: float | None = None
    ask: float | None = None
    last: float | None = None
    ts: float = 0.0

    @property
    def price(self) -> float | None:
        """Return the midpoint when available, otherwise the last trade."""
        if self.bid and self.ask and self.bid > 0 and self.ask > 0:
            return (self.bid + self.ask) / 2
        return self.last or None


@dataclass
class Bar:
    """Minute bar currently being built."""
    minute: int
    open: float
    high: float
    low: float
    close: float
    ticks: int = 1

    def update(self, px: float) -> None:
        self.high = max(self.high, px)
        self.low = min(self.low, px)
        self.close = px
        self.ticks += 1


@dataclass
class RealtimeQuotes:
    """Maintain the latest known price for each underlying via dxLink."""
    ticks: dict[str, Tick] = field(default_factory=dict)
    lock: threading.Lock = field(default_factory=threading.Lock)
    _state: str = "off"
    _detail: str = ""
    _started: bool = False

    _by_stream: dict[str, str] = field(default_factory=dict)




    _bar: dict[str, Bar] = field(default_factory=dict)
    _done: list[tuple[str, Bar]] = field(default_factory=list)


    def start(self) -> None:
        if self._started:
            return
        if not credentials_present():
            log.info("Spot temps réel désactivé (identifiants tastytrade absents)")
            self._state = "off"
            return
        self._started = True
        self._state = "connecting"
        threading.Thread(target=self._run, name="rtquote", daemon=True).start()
        log.info("Spot temps réel : démarrage du flux dxFeed")


    def price(self, key: str) -> float | None:
        """Return the latest known price for an internal key."""
        with self.lock:
            t = self.ticks.get(key)
            return t.price if t else None

    def status(self, market_open: bool = True) -> tuple[str, str]:
        """Return ``(state, detail)``; silence is degraded only during market hours."""
        if self._state == "off":
            return "off", ""
        if self._state != "connected":
            return "disconnected", self._detail
        with self.lock:
            newest = max((t.ts for t in self.ticks.values()), default=0.0)
        age = time.time() - newest if newest else None
        if age is None:
            return "degraded", "aucune cotation reçue"
        if market_open and age > STALE_S:
            return "degraded", f"aucun tick depuis {int(age)} s"
        return "connected", ""


    def _quote_token(self) -> tuple[str, str, str]:
        return quote_token()

    def _resolve_symbols(self, access: str) -> dict[str, str]:
        return resolve_symbols(access)

    def _run(self) -> None:
        backoff = BACKOFF_START
        while True:
            try:
                asyncio.run(self._session())
                backoff = BACKOFF_START
            except Exception as exc:
                self._state = "disconnected"
                self._detail = str(exc)[:120]
                log.warning("Flux dxFeed interrompu (%s) — reprise dans %.0f s",
                            exc, backoff)
            time.sleep(backoff)
            backoff = min(backoff * 2, BACKOFF_MAX)

    async def _session(self) -> None:
        import websockets

        token, url, access = self._quote_token()
        symbols = self._resolve_symbols(access)
        self._by_stream = {v: k for k, v in symbols.items()}

        async with websockets.connect(url, max_size=2 ** 22) as ws:
            async def send(m):
                await ws.send(json.dumps(m))

            await send({"type": "SETUP", "channel": 0, "version": "0.1-gex",
                        "keepaliveTimeout": 60, "acceptKeepaliveTimeout": 60})
            auth_sent = False









            subscribed = False

            async for raw in ws:
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
                    subs = [{"type": "Quote", "symbol": s} for s in symbols.values()]
                    subs += [{"type": "Trade", "symbol": s} for s in symbols.values()]
                    await send({"type": "FEED_SUBSCRIPTION", "channel": 1, "add": subs})
                    self._state = "connected"
                    self._detail = ""
                    log.info("Spot temps réel actif sur %s", ", ".join(symbols))
                elif typ == "FEED_DATA":
                    self._ingest(decode_compact_feed_data(m.get("data") or []))
                elif typ == "KEEPALIVE":
                    await send({"type": "KEEPALIVE", "channel": 0})
                elif typ == "ERROR":
                    log.warning("dxFeed ERROR : %s", str(m)[:200])

    def _ingest(self, data: list) -> None:
        now = time.time()
        minute = int(now // 60) * 60
        with self.lock:
            for item in data:
                if not isinstance(item, dict):
                    continue
                key = self._by_stream.get(item.get("eventSymbol"))
                if not key:
                    continue
                t = self.ticks.setdefault(key, Tick())
                etype = item.get("eventType")
                if etype == "Quote":
                    bid, ask = item.get("bidPrice"), item.get("askPrice")

                    if isinstance(bid, (int, float)) and bid == bid:
                        t.bid = float(bid)
                    if isinstance(ask, (int, float)) and ask == ask:
                        t.ask = float(ask)
                elif etype == "Trade":
                    px = item.get("price")
                    if isinstance(px, (int, float)) and px == px:
                        t.last = float(px)
                t.ts = now
                self._accumulate(key, t.price, minute)

    def _accumulate(self, key: str, px: float | None, minute: int) -> None:
        """Update the current minute bar and close the previous one."""
        if px is None:
            return
        cur = self._bar.get(key)
        if cur is None:
            self._bar[key] = Bar(minute, px, px, px, px)
        elif cur.minute == minute:
            cur.update(px)
        else:
            self._done.append((key, cur))
            self._bar[key] = Bar(minute, px, px, px, px)

    def drain_bars(self, flush: bool = False, now: float | None = None
                   ) -> list[tuple[str, Bar]]:
        """Return completed bars; ``flush`` also closes the current minute."""
        current = int((now if now is not None else time.time()) // 60) * 60
        with self.lock:
            out, self._done = self._done, []
            for key in list(self._bar):
                if flush or self._bar[key].minute < current:
                    out.append((key, self._bar.pop(key)))
        return out


QUOTES = RealtimeQuotes()


@dataclass
class PublicDelayedQuotes(RealtimeQuotes):
    """Free delayed (~15–20 minute) NQ/ES quotes from public dxFeed.

    Runs only without broker credentials and reuses the authenticated session
    protocol, replacing token and active-contract resolution with local logic.
    """

    def start(self) -> None:
        if self._started:
            return
        if credentials_present():
            return
        self._started = True
        self._state = "connecting"
        threading.Thread(target=self._run, name="rtquote-public", daemon=True).start()
        log.info("Spot NQ/ES délayé (public, sans compte) : démarrage")

    def _quote_token(self) -> tuple[str, str, str]:



        return "demo", PUBLIC_DEMO_URL, ""

    def _resolve_symbols(self, access: str) -> dict[str, str]:
        code = front_quarterly_code()
        return {"NQ": f"/NQ{code}:XCME", "ES": f"/ES{code}:XCME"}


PUBLIC_QUOTES = PublicDelayedQuotes()
