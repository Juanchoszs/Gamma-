from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def credentials_present() -> bool:
    return False


class TickCapture:
    def __init__(self) -> None:
        self._buf: dict[str, dict[str, list[dict]]] = {}
        self._started = False

    def start(self) -> None:
        if not credentials_present():
            self._started = False
            return
        self._started = True

    def record(self, universe: dict[str, tuple[str, str]], event: dict[str, Any], now: float | None = None) -> None:
        stream = event.get("eventSymbol")
        if not stream:
            return
        mapped = universe.get(stream)
        if mapped is None:
            return
        symbol, contract = mapped
        row = {
            "ts": float(event.get("time", now or 0.0)) / 1000.0 if "time" in event else float(now or 0.0),
            "price": float(event.get("price")) if event.get("price") is not None and str(event.get("price")) != "nan" else None,
            "volume": int(event.get("size") or 0),
            "bid": event.get("bidPrice"),
            "ask": event.get("askPrice"),
            "side": event.get("aggressorSide"),
            "source": "dxfeed",
        }
        if row["price"] is None:
            return
        self._buf.setdefault(symbol, {}).setdefault(contract, []).append(row)

    def drain(self):
        out = self._buf
        self._buf = {}
        return out

    def contract_order(self, symbol: str) -> list[str]:
        bucket = self._buf.get(symbol, {})
        return list(bucket.keys())


CAPTURE = TickCapture()

__all__ = ["CAPTURE", "TickCapture", "credentials_present"]
