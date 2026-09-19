"""Level inspector payloads for selected market-intelligence levels."""
from __future__ import annotations

from typing import Any, Iterable

from gex.application.market_intelligence.dto import market_level_to_dict
from gex.domain.market.intelligence import MarketLevel, Scenario


def build_level_inspector_payload(
    *,
    level: MarketLevel,
    spot: float,
    related_levels: Iterable[MarketLevel] = (),
    scenarios: Iterable[Scenario] = (),
) -> dict[str, Any]:
    """Build an API-ready explanation for a selected level.

    The inspector is deterministic UI state. It does not fetch data, recalculate
    GEX, or add probabilities.
    """
    levels = tuple(related_levels)
    scenario_refs = _related_scenarios(level, scenarios)
    payload: dict[str, Any] = {
        "level": market_level_to_dict(level),
        "summary": _summary(level),
        "metrics": _metrics(level),
        "context": _context(level, spot, levels, scenario_refs),
        "methodology": _methodology(level),
    }
    return payload


def _summary(level: MarketLevel) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": level.id,
        "type": level.level_type.value,
        "price": level.price,
        "source": level.source.value,
        "strength": level.strength,
        "session": level.session.value,
        "status": level.status.value,
    }
    _set_optional(payload, "distance_percent", level.distance_percent)
    return payload


def _metrics(level: MarketLevel) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for key, value in (
        ("open_interest", level.open_interest),
        ("volume", level.volume),
        ("gamma", level.gamma),
        ("delta", level.delta),
        ("vanna", level.vanna),
        ("charm", level.charm),
        ("expiration", level.expiration.isoformat() if level.expiration else None),
    ):
        _set_optional(payload, key, value)
    metadata = {
        key: value
        for key, value in level.metadata.items()
        if value is not None
    }
    _set_optional(payload, "metadata", metadata)
    return payload


def _context(
    level: MarketLevel,
    spot: float,
    related_levels: tuple[MarketLevel, ...],
    scenario_refs: tuple[dict[str, Any], ...],
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "spot": spot,
        "position": "ABOVE_SPOT" if level.price > spot else "BELOW_SPOT" if level.price < spot else "AT_SPOT",
        "related_scenarios": list(scenario_refs),
    }
    nearest_below = _nearest_below(level, related_levels)
    nearest_above = _nearest_above(level, related_levels)
    _set_optional(payload, "nearest_below", _level_reference(nearest_below))
    _set_optional(payload, "nearest_above", _level_reference(nearest_above))
    return payload


def _methodology(level: MarketLevel) -> dict[str, Any]:
    notes = [
        "Strength is a deterministic 0-100 score derived from available GEX, open interest, and volume inputs.",
        "Status and distance are produced by the market-state interaction rules for the current spot.",
        "Only source metrics present in the normalized level are included.",
    ]
    return {
        "source": level.source.value,
        "strength_score": level.strength,
        "notes": notes,
    }


def _related_scenarios(level: MarketLevel, scenarios: Iterable[Scenario]) -> tuple[dict[str, Any], ...]:
    refs: list[dict[str, Any]] = []
    for scenario in scenarios:
        key_match = scenario.key_level is not None and scenario.key_level.id == level.id
        next_match = any(next_level.id == level.id for next_level in scenario.next_levels)
        if not key_match and not next_match:
            continue
        refs.append({
            "id": scenario.id,
            "title": scenario.title,
            "direction": scenario.direction.value,
            "relationship": "KEY_LEVEL" if key_match else "NEXT_LEVEL",
            "trigger": scenario.trigger,
        })
    return tuple(refs)


def _nearest_below(level: MarketLevel, levels: tuple[MarketLevel, ...]) -> MarketLevel | None:
    candidates = [candidate for candidate in levels if candidate.id != level.id and candidate.price < level.price]
    if not candidates:
        return None
    return max(candidates, key=lambda candidate: (candidate.price, candidate.strength))


def _nearest_above(level: MarketLevel, levels: tuple[MarketLevel, ...]) -> MarketLevel | None:
    candidates = [candidate for candidate in levels if candidate.id != level.id and candidate.price > level.price]
    if not candidates:
        return None
    return min(candidates, key=lambda candidate: (candidate.price, -candidate.strength))


def _level_reference(level: MarketLevel | None) -> dict[str, Any] | None:
    if level is None:
        return None
    return {
        "id": level.id,
        "type": level.level_type.value,
        "price": level.price,
        "strength": level.strength,
        "status": level.status.value,
    }


def _set_optional(payload: dict[str, Any], key: str, value: Any) -> None:
    if value is None:
        return
    if value == {}:
        return
    payload[key] = value
