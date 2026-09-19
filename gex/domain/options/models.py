"""Normalized option-domain records shared by data adapters and application services."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class OptionType(StrEnum):
    CALL = "CALL"
    PUT = "PUT"


class FlowSide(StrEnum):
    BUY = "BUY"
    SELL = "SELL"
    UNKNOWN = "UNKNOWN"


class FlowAggressiveness(StrEnum):
    AGGRESSIVE = "AGGRESSIVE"
    PASSIVE = "PASSIVE"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class OptionContract:
    symbol: str
    underlying: str
    strike: float
    expiration: datetime | None
    option_type: OptionType
    bid: float | None = None
    ask: float | None = None
    last: float | None = None
    volume: float | None = None
    open_interest: float | None = None
    implied_volatility: float | None = None
    delta: float | None = None
    gamma: float | None = None
    theta: float | None = None
    vega: float | None = None
    contract_multiplier: float | None = None


@dataclass(frozen=True)
class OptionsFlowEvent:
    symbol: str
    timestamp: datetime
    strike: float
    expiration: datetime | None
    option_type: OptionType
    price: float
    quantity: float
    premium: float
    volume: float | None = None
    open_interest: float | None = None
    implied_volatility: float | None = None
    delta: float | None = None
    gamma: float | None = None
    side: FlowSide = FlowSide.UNKNOWN
    aggressiveness: FlowAggressiveness = FlowAggressiveness.UNKNOWN


def option_type_from_value(value: object) -> OptionType | None:
    text = str(value or "").strip().upper()
    if text in {"C", "CALL", "CALLS"}:
        return OptionType.CALL
    if text in {"P", "PUT", "PUTS"}:
        return OptionType.PUT
    return None


def flow_side_from_value(value: object) -> FlowSide:
    text = str(value or "").strip().upper()
    if text == "BUY":
        return FlowSide.BUY
    if text == "SELL":
        return FlowSide.SELL
    return FlowSide.UNKNOWN


def flow_aggressiveness_from_value(value: object) -> FlowAggressiveness:
    text = str(value or "").strip().upper()
    if text in {"AGGRESSIVE", "AGGRO", "A"}:
        return FlowAggressiveness.AGGRESSIVE
    if text in {"PASSIVE", "P"}:
        return FlowAggressiveness.PASSIVE
    return FlowAggressiveness.UNKNOWN
