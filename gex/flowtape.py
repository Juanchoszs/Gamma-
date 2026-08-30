"""Signed option order flow from dxFeed TimeAndSale events.

Spread legs (about 23% of SPX prints) remain separate from directional flow,
and all aggregates are size-weighted. The ±1.5% window and two expiries
produce about 39 QQQ, 32 SPY, and 31 SPX prints per second, so raw prints
stay in memory while one-minute bars are persisted. Broker data is personal.
"""
from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from collections import deque
from dataclasses import dataclass, field

import requests

from .config import CONTRACT_MULTIPLIER
from .rtquote import (
    BACKOFF_MAX,
    BACKOFF_START,
    QUOTES,
    credentials_present,
    quote_token,
)

log = logging.getLogger(__name__)





TRACKED: dict[str, str] = {
    "SPX": "index", "NDX": "index", "SPY": "index", "QQQ": "index",
    "ES": "future", "NQ": "future",
}





STRIKE_WINDOW = 0.015
MAX_EXPIRIES = 2





UNIVERSE_REFRESH_S = 1800









RECENTER_FRACTION = 0.5


DRIFT_CHECK_S = 5.0

INDEX_CHAIN_URL = "https://api.tastyworks.com/option-chains/{symbol}/nested"












PRINT_BUFFER = 5000


@dataclass
class FlowBar:
    """One-minute aggregate for an underlying."""
    minute: int

    net_contracts: float = 0.0
    net_premium: float = 0.0
    net_calls: float = 0.0
    net_puts: float = 0.0

    net_delta: float = 0.0
    delta_prints: int = 0
    no_delta_prints: int = 0


    net_gamma: float = 0.0
    net_gamma_calls: float = 0.0
    net_gamma_puts: float = 0.0
    buy_contracts: float = 0.0
    sell_contracts: float = 0.0
    prints: int = 0
    spread_contracts: float = 0.0
    spread_prints: int = 0
    undefined_prints: int = 0

    def as_row(self, symbol: str, timestamp) -> dict:
        return {
            "timestamp": timestamp, "symbol": symbol,
            "net_contracts": self.net_contracts, "net_premium": self.net_premium,
            "net_calls": self.net_calls, "net_puts": self.net_puts,
            "net_delta": self.net_delta,
            "net_gamma": self.net_gamma,
            "net_gamma_calls": self.net_gamma_calls,
            "net_gamma_puts": self.net_gamma_puts,
            "delta_prints": float(self.delta_prints),
            "no_delta_prints": float(self.no_delta_prints),
            "buy_contracts": self.buy_contracts, "sell_contracts": self.sell_contracts,
            "prints": float(self.prints),
            "spread_contracts": self.spread_contracts,
            "spread_prints": float(self.spread_prints),
            "undefined_prints": float(self.undefined_prints),
            "source": "dxfeed",
        }


def option_type_of(streamer_symbol: str) -> str | None:
    """Extract the C/P type immediately preceding the numeric strike."""
    core = streamer_symbol.split(":")[0]
    for i in range(len(core) - 1, -1, -1):
        if core[i] in ("C", "P") and i + 1 < len(core) and core[i + 1].isdigit():
            return core[i]
    return None


def strike_of(streamer_symbol: str) -> float | None:
    """Extract the numeric strike from a streamer symbol."""
    core = streamer_symbol.split(":")[0]
    for i in range(len(core) - 1, -1, -1):
        if core[i] in ("C", "P") and i + 1 < len(core) and core[i + 1].isdigit():
            reste = core[i + 1:]
            try:
                return float(reste)
            except ValueError:
                return None
    return None


def multiplier_of(symbol: str) -> float:
    """Return the option dollar-per-point multiplier for a symbol."""
    from .futopt import _multiplier_cache
    return float(_multiplier_cache.get(symbol, CONTRACT_MULTIPLIER))


def build_index_universe(symbol: str, spot: float, access_token: str,
                         window: float = STRIKE_WINDOW,
                         max_expiries: int = MAX_EXPIRIES) -> list[str]:
    """Return streamer symbols for an index or ETF."""
    r = requests.get(INDEX_CHAIN_URL.format(symbol=symbol),
                     headers={"Authorization": f"Bearer {access_token}"}, timeout=90)
    r.raise_for_status()
    lo, hi = spot * (1 - window), spot * (1 + window)
    out: list[str] = []
    for item in r.json()["data"]["items"]:
        for exp in item.get("expirations", [])[:max_expiries]:
            for st in exp.get("strikes", []):
                if not lo <= float(st["strike-price"]) <= hi:
                    continue
                for key in ("call-streamer-symbol", "put-streamer-symbol"):
                    if st.get(key):
                        out.append(st[key])
    return out


def build_future_universe(code: str, spot: float, access_token: str,
                          window: float = STRIKE_WINDOW,
                          max_days: int = 5) -> list[str]:
    """Return streamer symbols for futures options."""
    from .futopt import fetch_chain_instruments, filter_chain
    chain = fetch_chain_instruments(code, access_token)
    chain = filter_chain(chain, spot, window, max_days)
    return chain["streamer_symbol"].tolist() if not chain.empty else []


@dataclass
class FlowTape:
    """Collect signed prints and aggregate them into one-minute bars."""
    bars: dict[str, FlowBar] = field(default_factory=dict)
    done: list[tuple[str, FlowBar]] = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)
    _by_stream: dict[str, str] = field(default_factory=dict)





    _delta: dict[str, float] = field(default_factory=dict)
    _gamma: dict[str, float] = field(default_factory=dict)




    _spot: dict[str, float] = field(default_factory=dict)



    _prints: dict[str, deque] = field(default_factory=dict)




    _center: dict[str, float] = field(default_factory=dict)
    _started: bool = False
    _state: str = "off"

    def _drifted(self) -> str | None:
        """Return the first underlying whose live spot moved beyond its center."""
        seuil = STRIKE_WINDOW * RECENTER_FRACTION
        with self.lock:
            centres = dict(self._center)
        for symbol, centre in centres.items():
            live = QUOTES.price(symbol)
            if live and centre and abs(live - centre) / centre > seuil:
                return symbol
        return None

    def ingest_print(self, item: dict, now: float) -> None:
        """Add a print to its minute bar; this is the network-free test seam."""
        stream = item.get("eventSymbol")
        symbol = self._by_stream.get(stream)
        if symbol is None:
            return
        size = item.get("size")
        price = item.get("price")
        if not isinstance(size, (int, float)) or size != size or size <= 0:
            return

        minute = int(now // 60) * 60
        with self.lock:
            bar = self.bars.get(symbol)
            if bar is None:
                self.bars[symbol] = bar = FlowBar(minute)
            elif bar.minute != minute:
                self.done.append((symbol, bar))
                self.bars[symbol] = bar = FlowBar(minute)

            bar.prints += 1
            size = float(size)




            self._record_print(symbol, stream, item, price, size, now)



            if item.get("spreadLeg"):
                bar.spread_contracts += size
                bar.spread_prints += 1
                return

            side = item.get("aggressorSide")
            if side == "BUY":
                sign = 1.0
            elif side == "SELL":
                sign = -1.0
            else:


                bar.undefined_prints += 1
                return








            typ = option_type_of(stream or "")




            type_sign = 1.0 if typ == "C" else -1.0 if typ == "P" else 0.0



            dealer_contracts = sign * type_sign * size
            bar.net_contracts += dealer_contracts
            if typ == "C":
                bar.net_calls += dealer_contracts
            elif typ == "P":
                bar.net_puts += dealer_contracts

            if sign > 0:
                bar.buy_contracts += size
            else:
                bar.sell_contracts += size

            mult = multiplier_of(symbol)



            if isinstance(price, (int, float)) and price == price:
                bar.net_premium += sign * size * float(price) * mult







            delta = self._delta.get(stream)
            spot = self._spot.get(symbol)
            if delta is None or not spot:
                bar.no_delta_prints += 1
            else:
                bar.net_delta += -sign * size * delta * mult * spot
                bar.delta_prints += 1







            gamma = self._gamma.get(stream)
            if gamma is not None and spot and type_sign:
                g = sign * type_sign * size * gamma * mult * spot ** 2 * 0.01
                bar.net_gamma += g
                if typ == "C":
                    bar.net_gamma_calls += g
                elif typ == "P":
                    bar.net_gamma_puts += g

    def _record_print(self, symbol: str, stream: str, item: dict,
                      price, size: float, now: float) -> None:
        """Append a print to the tape buffer under ``self.lock``."""
        side = item.get("aggressorSide")
        px = float(price) if isinstance(price, (int, float)) and price == price else None
        notional = (px * size * multiplier_of(symbol)) if px is not None else None
        buf = self._prints.get(symbol)
        if buf is None:
            buf = self._prints[symbol] = deque(maxlen=PRINT_BUFFER)
        buf.append({
            "t": now,
            "symbol": symbol,
            "strike": strike_of(stream or ""),
            "type": option_type_of(stream or ""),
            "price": px,
            "size": size,
            "side": side if side in ("BUY", "SELL") else "?",
            "notional": notional,
            "combo": bool(item.get("spreadLeg")),
        })

    def recent_prints(self, symbol: str, min_size: float = 0.0,
                      include_combos: bool = True, limit: int = 60) -> list[dict]:
        """Return recent prints, newest first, as copies safe for Dash callbacks."""
        with self.lock:
            buf = list(self._prints.get(symbol, ()))
        out = []
        for rec in reversed(buf):
            if rec["size"] < min_size:
                continue
            if rec["combo"] and not include_combos:
                continue
            out.append(dict(rec))
            if len(out) >= limit:
                break
        return out

    def ingest_greeks(self, item: dict) -> None:
        """Store the current delta and gamma for a contract."""
        stream = item.get("eventSymbol")
        if stream not in self._by_stream:
            return
        for champ, cible in (("delta", self._delta), ("gamma", self._gamma)):
            v = item.get(champ)
            if isinstance(v, (int, float)) and v == v:
                cible[stream] = float(v)

    def drain_bars(self, flush: bool = False) -> list[tuple[str, FlowBar]]:
        """Return completed bars; ``flush`` also emits bars still in progress."""
        with self.lock:
            out = self.done
            self.done = []
            if flush:
                out += list(self.bars.items())
                self.bars = {}
        return out





    def status(self) -> tuple[str, int]:
        """Return ``(state, tracked_contract_count)`` for display."""
        return self._state, len(self._by_stream)

    def start(self) -> None:
        if self._started:
            return
        if not credentials_present():
            log.info("Order flow options désactivé (identifiants absents)")
            self._state = "off"
            return
        self._started = True
        self._state = "connecting"
        threading.Thread(target=self._run, name="flowtape", daemon=True).start()

    def _build_universe(self) -> dict[str, str]:
        """Build the streamer-to-underlying map for all tracked markets."""
        from . import futopt, idxopt

        _, _, access = quote_token()
        out: dict[str, str] = {}
        spots: dict[str, float] = {}
        for symbol, kind in TRACKED.items():
            try:
                if kind == "future":
                    spot = futopt._reference_spot(symbol, access)
                    syms = (build_future_universe(symbol, spot, access)
                            if spot else [])
                else:
                    spot = idxopt.reference_spot(symbol)
                    syms = (build_index_universe(symbol, spot, access)
                            if spot else [])
                if spot:
                    spots[symbol] = float(spot)
                for s in syms:
                    out[s] = symbol
            except Exception:
                log.exception("%s : univers de flux indisponible", symbol)
        with self.lock:
            self._spot.update(spots)


            self._center = dict(spots)
        return out

    def _run(self) -> None:
        backoff = BACKOFF_START
        while True:
            try:
                asyncio.run(self._session())
                backoff = BACKOFF_START
            except Exception as exc:
                self._state = "disconnected"
                log.warning("Order flow options interrompu (%s) — reprise dans %.0f s",
                            exc, backoff)
                time.sleep(backoff)
                backoff = min(backoff * 2, BACKOFF_MAX)

    async def _session(self) -> None:
        """Build the universe, subscribe once, and listen until refresh."""
        import websockets

        token, url, _ = quote_token()
        universe = self._build_universe()
        if not universe:
            self._state = "degraded"
            raise RuntimeError("aucun contrat à suivre")
        with self.lock:
            self._by_stream = universe

        async with websockets.connect(url, max_size=2 ** 24, ping_interval=None) as ws:
            async def send(m):
                await ws.send(json.dumps(m))

            await send({"type": "SETUP", "channel": 0, "version": "0.1-flow",
                        "keepaliveTimeout": 60, "acceptKeepaliveTimeout": 60})
            auth_sent = False


            subscribed = False
            deadline = time.monotonic() + UNIVERSE_REFRESH_S
            next_drift_check = time.monotonic() + DRIFT_CHECK_S

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


                    await send({"type": "FEED_SETUP", "channel": 1,
                                "acceptAggregationPeriod": 0.0,
                                "acceptDataFormat": "FULL"})
                elif typ == "FEED_CONFIG" and not subscribed:
                    subscribed = True



                    await send({"type": "FEED_SUBSCRIPTION", "channel": 1,
                                "add": [{"type": e, "symbol": s}
                                        for s in universe
                                        for e in ("TimeAndSale", "Greeks")]})
                    self._state = "connected"
                    log.info("Order flow options actif — %d contrats sur %s",
                             len(universe), ", ".join(TRACKED))
                elif typ == "KEEPALIVE":
                    await send({"type": "KEEPALIVE", "channel": 0})
                elif typ == "ERROR":
                    log.warning("dxFeed ERROR (order flow) : %s", str(m)[:200])
                elif typ == "FEED_DATA":
                    now = time.time()
                    for item in m.get("data") or []:
                        if not isinstance(item, dict):
                            continue
                        etype = item.get("eventType")
                        if etype == "Greeks":
                            self.ingest_greeks(item)
                        elif etype == "TimeAndSale":
                            self.ingest_print(item, now)

                now_mono = time.monotonic()
                if now_mono > deadline:
                    log.info("Order flow : renouvellement périodique de l'univers")
                    return



                if subscribed and now_mono > next_drift_check:
                    next_drift_check = now_mono + DRIFT_CHECK_S
                    derive = self._drifted()
                    if derive is not None:
                        log.info("Order flow : %s a dérivé hors fenêtre — "
                                 "recentrage de l'univers", derive)
                        return


TAPE = FlowTape()
