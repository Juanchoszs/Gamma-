"""Serializable DTOs for GAMMA market-intelligence outputs."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Mapping

from gex.application.market_intelligence.service import MarketIntelligenceSnapshot
from gex.domain.market.intelligence import (
    MarketLevel,
    MarketReport,
    MarketState,
    Scenario,
)


def snapshot_to_dict(snapshot: MarketIntelligenceSnapshot) -> dict[str, Any]:
    """Convert a market-intelligence snapshot into an API-ready structure."""
    return {
        "state": market_state_to_dict(snapshot.state),
        "scenarios": [scenario_to_dict(scenario) for scenario in snapshot.scenarios],
        "report": market_report_to_dict(snapshot.report),
    }


def market_report_to_dict(report: MarketReport) -> dict[str, Any]:
    return {
        "symbol": report.symbol,
        "timestamp": _iso(report.timestamp),
        "market_state": market_state_to_dict(report.market_state),
        "key_levels": [market_level_to_dict(level) for level in report.key_levels],
        "scenarios": [scenario_to_dict(scenario) for scenario in report.scenarios],
        "positioning_summary": list(report.positioning_summary),
        "structure_summary": list(report.structure_summary),
    }


def market_state_to_dict(state: MarketState) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "symbol": state.symbol,
        "timestamp": _iso(state.timestamp),
        "spot": state.spot,
        "gamma_regime": state.gamma_regime.value,
        "structure": state.structure.value,
        "session": state.session.value,
        "data_status": state.data_status,
        "reasons": list(state.reasons),
    }
    _set_optional(payload, "previous_spot", state.previous_spot)
    _set_optional(payload, "price_change", state.price_change)
    _set_optional(payload, "price_change_percent", state.price_change_percent)
    _set_optional(payload, "implied_volatility", state.implied_volatility)
    _set_optional(payload, "positioning", state.positioning if state.positioning != "UNKNOWN" else None)
    _set_optional(payload, "nearest_support", _maybe_level(state.nearest_support))
    _set_optional(payload, "nearest_resistance", _maybe_level(state.nearest_resistance))
    _set_optional(payload, "major_gamma_level", _maybe_level(state.major_gamma_level))
    return payload


def scenario_to_dict(scenario: Scenario) -> dict[str, Any]:
    return {
        "id": scenario.id,
        "title": scenario.title,
        "direction": scenario.direction.value,
        "trigger": scenario.trigger,
        "key_level": _maybe_level(scenario.key_level),
        "conditions": list(scenario.conditions),
        "structural_implication": scenario.structural_implication,
        "invalidation": scenario.invalidation,
        "next_levels": [market_level_to_dict(level) for level in scenario.next_levels],
        "supporting_data": _clean_mapping(scenario.supporting_data),
    }


def market_level_to_dict(level: MarketLevel) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": level.id,
        "type": level.level_type.value,
        "price": level.price,
        "source": level.source.value,
        "timestamp": _iso(level.timestamp),
        "strength": level.strength,
        "session": level.session.value,
        "status": level.status.value,
    }
    optional_values = {
        "distance_percent": level.distance_percent,
        "expiration": _maybe_iso(level.expiration),
        "volume": level.volume,
        "open_interest": level.open_interest,
        "gamma": level.gamma,
        "delta": level.delta,
        "vanna": level.vanna,
        "charm": level.charm,
        "metadata": _clean_mapping(level.metadata),
    }
    for key, value in optional_values.items():
        _set_optional(payload, key, value)
    return payload


def _maybe_level(level: MarketLevel | None) -> dict[str, Any] | None:
    if level is None:
        return None
    return market_level_to_dict(level)


def _set_optional(payload: dict[str, Any], key: str, value: Any) -> None:
    if value is None:
        return
    if value == {}:
        return
    payload[key] = value


def _clean_mapping(mapping: Mapping[str, object]) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    for key, value in mapping.items():
        cleaned[key] = _clean_value(value)
    return {key: value for key, value in cleaned.items() if value is not None}


def _clean_value(value: object) -> Any:
    if isinstance(value, datetime):
        return _iso(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return _clean_mapping(value)
    if isinstance(value, tuple | list):
        return [_clean_value(item) for item in value if item is not None]
    return value


def _maybe_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return _iso(value)


def _iso(value: datetime) -> str:
    return value.isoformat()
