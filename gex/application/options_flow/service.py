"""Prepare normalized options flow for the price/GEX overlay renderer."""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable

import pandas as pd
from gex.domain.options.models import (
    FlowAggressiveness,
    FlowSide,
    OptionType,
    OptionsFlowEvent,
    flow_aggressiveness_from_value,
    flow_side_from_value,
    option_type_from_value,
)

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class OptionsFlowOverlayConfig:
    min_premium: float = 0.0
    min_volume: float = 0.0
    min_significance: float = 0.0
    min_bubble_size: float = 8.0
    max_bubble_size: float = 34.0
    aggregation_seconds: int = 60
    max_bubbles: int = 250
    option_types: frozenset[OptionType] = field(
        default_factory=lambda: frozenset({OptionType.CALL, OptionType.PUT})
    )
    sides: frozenset[FlowSide] = field(
        default_factory=lambda: frozenset({FlowSide.BUY, FlowSide.SELL, FlowSide.UNKNOWN})
    )
    visible_strike_range: float | None = None
    expiration_filter: str = "ALL"


@dataclass(frozen=True)
class FlowBubble:
    timestamp: datetime
    strike: float
    option_type: OptionType
    size: float
    premium: float
    volume: float
    event_count: int
    average_price: float | None
    expiration: datetime | None = None
    open_interest: float | None = None
    implied_volatility: float | None = None
    delta: float | None = None
    gamma: float | None = None
    side: FlowSide = FlowSide.UNKNOWN
    aggressiveness: FlowAggressiveness = FlowAggressiveness.UNKNOWN
    color_state: str = "neutral"
    tooltip: dict[str, object] = field(default_factory=dict)


def premium_for(price: float, quantity: float, contract_multiplier: float | None) -> float:
    multiplier = 100.0 if contract_multiplier is None else float(contract_multiplier)
    return max(0.0, float(price)) * max(0.0, float(quantity)) * max(0.0, multiplier)


def events_from_records(
    records: Iterable[dict] | pd.DataFrame,
    *,
    symbol: str,
    contract_multiplier: float | None = None,
) -> list[OptionsFlowEvent]:
    frame = records if isinstance(records, pd.DataFrame) else pd.DataFrame(list(records))
    if frame.empty:
        return []
    events: list[OptionsFlowEvent] = []
    skipped = 0
    for row in frame.to_dict("records"):
        option_type = option_type_from_value(row.get("option_type", row.get("type")))
        if option_type is None:
            skipped += 1
            continue
        try:
            timestamp = pd.to_datetime(row.get("timestamp", row.get("time", row.get("t")))).to_pydatetime()
            strike = float(row.get("strike"))
            price = float(row.get("price"))
            quantity = float(row.get("quantity", row.get("size", row.get("volume", 0.0))))
        except (TypeError, ValueError):
            skipped += 1
            continue
        if strike <= 0 or price < 0 or quantity < 0:
            skipped += 1
            continue
        row_multiplier = _optional_float(row.get("contract_multiplier", row.get("multiplier")))
        effective_multiplier = row_multiplier if row_multiplier is not None else contract_multiplier
        premium = row.get("premium", row.get("notional"))
        try:
            premium_value = float(premium) if premium is not None else premium_for(price, quantity, effective_multiplier)
        except (TypeError, ValueError):
            premium_value = premium_for(price, quantity, effective_multiplier)
        if premium_value < 0:
            skipped += 1
            continue
        expiration = row.get("expiration", row.get("expiry"))
        expiration_dt = None
        if expiration is not None and not pd.isna(expiration):
            expiration_dt = pd.to_datetime(expiration).to_pydatetime()
        volume = _optional_float(row.get("volume", quantity))
        open_interest = _optional_float(row.get("open_interest"))
        if (volume is not None and volume < 0) or (open_interest is not None and open_interest < 0):
            skipped += 1
            continue
        events.append(OptionsFlowEvent(
            symbol=str(row.get("symbol") or symbol),
            timestamp=timestamp,
            strike=strike,
            expiration=expiration_dt,
            option_type=option_type,
            price=price,
            quantity=quantity,
            premium=premium_value,
            volume=volume,
            open_interest=open_interest,
            implied_volatility=_optional_float(row.get("implied_volatility", row.get("iv"))),
            delta=_optional_float(row.get("delta")),
            gamma=_optional_float(row.get("gamma")),
            side=flow_side_from_value(row.get("side")),
            aggressiveness=flow_aggressiveness_from_value(
                _first_present(row, "aggressiveness", "aggression")
            ),
        ))
    log.info(
        "Received %s options-flow records for %s; normalized %s events",
        len(frame),
        symbol,
        len(events),
    )
    if skipped:
        log.info("Skipped %s invalid options-flow records for %s", skipped, symbol)
    return events


def build_flow_bubbles(
    events: Iterable[OptionsFlowEvent],
    *,
    current_price: float | None = None,
    config: OptionsFlowOverlayConfig | None = None,
) -> list[FlowBubble]:
    cfg = config or OptionsFlowOverlayConfig()
    filtered = [event for event in events if _event_visible(event, current_price, cfg)]
    if not filtered:
        return []
    rows = []
    interval = max(1, int(cfg.aggregation_seconds))
    for event in filtered:
        rows.append({
            "timestamp": pd.Timestamp(event.timestamp).floor(f"{interval}s"),
            "strike": event.strike,
            "expiration": event.expiration,
            "option_type": event.option_type,
            "side": event.side,
            "aggressiveness": event.aggressiveness,
            "price": event.price,
            "quantity": event.quantity,
            "premium": event.premium,
            "volume": event.volume if event.volume is not None else event.quantity,
            "open_interest": event.open_interest,
            "implied_volatility": event.implied_volatility,
            "delta": event.delta,
            "gamma": event.gamma,
        })
    frame = pd.DataFrame(rows)
    grouped = frame.groupby(
        ["timestamp", "strike", "option_type", "expiration", "side", "aggressiveness"],
        dropna=False,
    )
    aggregates = grouped.agg(
        premium=("premium", "sum"),
        volume=("volume", "sum"),
        event_count=("premium", "size"),
        average_price=("price", "mean"),
        open_interest=("open_interest", "max"),
        implied_volatility=("implied_volatility", "mean"),
        delta=("delta", "mean"),
        gamma=("gamma", "mean"),
    ).reset_index()
    aggregates = aggregates.sort_values("premium", ascending=False).head(max(1, cfg.max_bubbles))
    max_premium = float(aggregates["premium"].max()) if not aggregates.empty else 0.0
    bubbles: list[FlowBubble] = []
    for row in aggregates.to_dict("records"):
        option_type = row["option_type"] if isinstance(row["option_type"], OptionType) else OptionType(str(row["option_type"]))
        side = row["side"] if isinstance(row["side"], FlowSide) else flow_side_from_value(row["side"])
        aggressiveness = (
            row["aggressiveness"]
            if isinstance(row["aggressiveness"], FlowAggressiveness)
            else flow_aggressiveness_from_value(row["aggressiveness"])
        )
        premium = float(row["premium"])
        volume = float(row["volume"]) if row["volume"] == row["volume"] else 0.0
        size = _bubble_size(premium, max_premium, cfg)
        color_state = _color_state(option_type, side)
        expiration = None if pd.isna(row["expiration"]) else pd.Timestamp(row["expiration"]).to_pydatetime()
        bubbles.append(FlowBubble(
            timestamp=pd.Timestamp(row["timestamp"]).to_pydatetime(),
            strike=float(row["strike"]),
            option_type=option_type,
            size=size,
            premium=premium,
            volume=volume,
            event_count=int(row["event_count"]),
            average_price=_optional_float(row["average_price"]),
            expiration=expiration,
            open_interest=_optional_float(row["open_interest"]),
            implied_volatility=_optional_float(row["implied_volatility"]),
            delta=_optional_float(row["delta"]),
            gamma=_optional_float(row["gamma"]),
            side=side,
            aggressiveness=aggressiveness,
            color_state=color_state,
            tooltip=_bubble_tooltip(
                option_type=option_type,
                strike=float(row["strike"]),
                premium=premium,
                volume=volume,
                event_count=int(row["event_count"]),
                average_price=_optional_float(row["average_price"]),
                expiration=expiration,
                open_interest=_optional_float(row["open_interest"]),
                implied_volatility=_optional_float(row["implied_volatility"]),
                delta=_optional_float(row["delta"]),
                gamma=_optional_float(row["gamma"]),
                side=side,
                aggressiveness=aggressiveness,
            ),
        ))
    log.info("Aggregated %s flow events into %s overlay bubbles", len(filtered), len(bubbles))
    return sorted(bubbles, key=lambda bubble: bubble.timestamp)


def _event_visible(
    event: OptionsFlowEvent,
    current_price: float | None,
    cfg: OptionsFlowOverlayConfig,
) -> bool:
    if event.option_type not in cfg.option_types:
        return False
    if event.side not in cfg.sides:
        return False
    if event.premium < cfg.min_premium:
        return False
    if (event.volume or event.quantity) < cfg.min_volume:
        return False
    if cfg.min_significance and event.premium < cfg.min_significance:
        return False
    if not _expiration_visible(event, cfg.expiration_filter):
        return False
    if cfg.visible_strike_range and current_price and current_price > 0:
        low = current_price * (1.0 - cfg.visible_strike_range)
        high = current_price * (1.0 + cfg.visible_strike_range)
        if not low <= event.strike <= high:
            return False
    return True


def _expiration_visible(event: OptionsFlowEvent, expiration_filter: str) -> bool:
    raw_filter = str(expiration_filter or "ALL").strip()
    bucket = raw_filter.upper()
    if bucket == "ALL":
        return True
    if event.expiration is None:
        return False
    dte = (event.expiration.date() - event.timestamp.date()).days
    if dte < 0:
        return False
    if bucket == "0DTE":
        return dte == 0
    if bucket == "1DTE":
        return dte == 1
    if bucket == "WEEKLY":
        return 2 <= dte <= 7
    if bucket == "MONTHLY":
        return 8 <= dte <= 45
    custom_value = raw_filter.split(":", 1)[1] if bucket.startswith("CUSTOM:") else raw_filter
    try:
        custom_expiration = pd.to_datetime(custom_value).date()
    except (TypeError, ValueError):
        return False
    return event.expiration.date() == custom_expiration


def _bubble_size(premium: float, max_premium: float, cfg: OptionsFlowOverlayConfig) -> float:
    if max_premium <= 0:
        return cfg.min_bubble_size
    ratio = math.log1p(max(0.0, premium)) / math.log1p(max_premium)
    ratio = min(1.0, max(0.0, ratio))
    return cfg.min_bubble_size + (cfg.max_bubble_size - cfg.min_bubble_size) * ratio


def _color_state(option_type: OptionType, side: FlowSide) -> str:
    prefix = "call" if option_type is OptionType.CALL else "put"
    if side is FlowSide.BUY:
        return f"{prefix}_buy"
    if side is FlowSide.SELL:
        return f"{prefix}_sell"
    return f"{prefix}_unknown"


def _bubble_tooltip(
    *,
    option_type: OptionType,
    strike: float,
    premium: float,
    volume: float,
    event_count: int,
    average_price: float | None,
    expiration: datetime | None,
    open_interest: float | None,
    implied_volatility: float | None,
    delta: float | None,
    gamma: float | None,
    side: FlowSide,
    aggressiveness: FlowAggressiveness,
) -> dict[str, object]:
    tooltip: dict[str, object] = {
        "option_type": option_type.value,
        "strike": strike,
        "premium": premium,
        "volume": volume,
        "event_count": event_count,
        "side": side.value,
    }
    optional = {
        "average_price": average_price,
        "expiration": expiration,
        "open_interest": open_interest,
        "implied_volatility": implied_volatility,
        "delta": delta,
        "gamma": gamma,
    }
    tooltip.update({key: value for key, value in optional.items() if value is not None})
    if aggressiveness is not FlowAggressiveness.UNKNOWN:
        tooltip["aggressiveness"] = aggressiveness.value
    return tooltip


def _optional_float(value: object) -> float | None:
    try:
        if value is None or pd.isna(value):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _first_present(row: dict, *keys: str) -> object:
    for key in keys:
        value = row.get(key)
        if value is not None and not pd.isna(value):
            return value
    return None
