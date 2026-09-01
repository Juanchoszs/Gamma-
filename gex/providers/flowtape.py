from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from gex.config import CONTRACT_MULTIPLIER
from gex.providers.rtquote import QUOTES, quote_token

PRINT_BUFFER = 500
STRIKE_WINDOW = 0.015
RECENTER_FRACTION = 0.5


def option_type_of(symbol: str) -> str:
    match = re.search(r"([CP])\d", str(symbol or ""))
    if not match:
        raise ValueError(f"No option type in symbol: {symbol!r}")
    return match.group(1)


def strike_of(symbol: str) -> float:
    match = re.search(r"([CP])(\d+(?:\.\d+)?)", str(symbol or ""))
    if not match:
        raise ValueError(f"No strike in symbol: {symbol!r}")
    return float(match.group(2))


@dataclass
class _FlowBar:
    net_contracts: float = 0.0
    buy_contracts: float = 0.0
    sell_contracts: float = 0.0
    prints: int = 0
    spread_contracts: float = 0.0
    spread_prints: int = 0
    undefined_prints: int = 0
    net_calls: float = 0.0
    net_puts: float = 0.0
    net_premium: float = 0.0
    net_delta: float = 0.0
    no_delta_prints: int = 0

    def as_row(self, symbol: str, ts: Any) -> dict:
        return {
            "timestamp": ts,
            "symbol": symbol,
            "net_contracts": self.net_contracts,
            "buy_contracts": self.buy_contracts,
            "sell_contracts": self.sell_contracts,
            "prints": self.prints,
            "spread_contracts": self.spread_contracts,
            "spread_prints": self.spread_prints,
            "undefined_prints": self.undefined_prints,
            "net_calls": self.net_calls,
            "net_puts": self.net_puts,
            "net_premium": self.net_premium,
            "net_delta": self.net_delta,
            "source": "dxfeed",
        }


class FlowTape:
    def __init__(self) -> None:
        self._by_stream: dict[str, str] = {}
        self._delta: dict[str, float] = {}
        self._spot: dict[str, float] = {}
        self._center: dict[str, float] = {}
        self.bars: dict[str, _FlowBar] = {}
        self._prints: list[dict[str, Any]] = []

    def status(self):
        return ("connected", "")

    def ingest_greeks(self, payload: dict[str, Any]) -> None:
        sym = payload.get("eventSymbol")
        if not sym or sym not in self._by_stream:
            return
        if "delta" in payload:
            self._delta[sym] = float(payload["delta"])

    def ingest_print(self, event: dict[str, Any], now: float | None = None) -> None:
        now = time_value() if now is None else float(now)
        stream = event.get("eventSymbol")
        if not stream:
            return
        symbol = self._by_stream.get(stream)
        if symbol is None:
            return
        size = float(event.get("size", 0) or 0)
        if size <= 0:
            return
        side = event.get("aggressorSide")
        favorite = {"BUY": 1.0, "SELL": -1.0}.get(str(side).upper())
        spread = bool(event.get("spreadLeg"))
        price = float(event.get("price", 0.0) or 0.0)
        # Rebuild the current bar for the symbol.
        bar = self.bars.setdefault(symbol, _FlowBar())
        if spread:
            bar.spread_contracts += size
            bar.spread_prints += 1
        else:
            if favorite is None:
                bar.undefined_prints += 1
            else:
                bar.buy_contracts += size if favorite > 0 else 0.0
                bar.sell_contracts += size if favorite < 0 else 0.0
                bar.net_contracts += favorite * size
                if option_type_of(stream) == "C":
                    bar.net_calls += favorite * size
                else:
                    bar.net_puts += -favorite * size
                bar.net_premium += favorite * size * price * CONTRACT_MULTIPLIER
                spot = self._spot.get(symbol, 1.0)
                delta = self._delta.get(stream)
                if delta is not None:
                    bar.net_delta += -favorite * size * float(delta) * CONTRACT_MULTIPLIER * spot
                else:
                    bar.no_delta_prints += 1
        bar.prints += 1
        self._prints.append({
            "t": float(now),
            "symbol": symbol,
            "stream": stream,
            "side": {"BUY": "BUY", "SELL": "SELL"}.get(str(side).upper(), "?"),
            "size": size,
            "price": price,
            "combo": spread,
            "type": option_type_of(stream),
            "strike": strike_of(stream),
            "notional": price * size * CONTRACT_MULTIPLIER,
        })
        self._prints = self._prints[-PRINT_BUFFER:]

    def drain_bars(self, flush: bool = False, now: float | None = None) -> list[tuple[str, _FlowBar]]:
        if not self.bars:
            return []
        done: list[tuple[str, _FlowBar]] = []
        for symbol, bar in list(self.bars.items()):
            done.append((symbol, bar))
            del self.bars[symbol]
        return done if flush else []

    def recent_prints(self, symbol: str, min_size: float = 0.0, limit: int = PRINT_BUFFER, include_combos: bool = True):
        rows = []
        for entry in reversed(self._prints):
            if entry["symbol"] != symbol:
                continue
            if entry["size"] < min_size:
                continue
            if not include_combos and entry["combo"]:
                continue
            rows.append(entry)
            if len(rows) >= limit:
                break
        return rows

    def _drifted(self):
        for symbol, center in self._center.items():
            live = QUOTES.price(symbol)
            if live is None:
                continue
            if abs(live - center) > center * STRIKE_WINDOW * RECENTER_FRACTION:
                return symbol
        return None

    def _build_universe(self):
        self._center = {}


TAPE = FlowTape()


def time_value() -> float:
    import time as _time
    return _time.time()


__all__ = [
    "PRINT_BUFFER",
    "RECENTER_FRACTION",
    "STRIKE_WINDOW",
    "FlowTape",
    "TAPE",
    "option_type_of",
    "strike_of",
]
