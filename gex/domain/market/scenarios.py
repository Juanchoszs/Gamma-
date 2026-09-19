"""Conditional scenario generation from market state and normalized levels."""
from __future__ import annotations

from typing import Iterable

from gex.domain.market.intelligence import (
    LevelType,
    MarketLevel,
    MarketState,
    MarketStructure,
    Scenario,
    ScenarioDirection,
)


SUPPORT_TYPES = {
    LevelType.PUT_WALL,
    LevelType.VAL,
    LevelType.OVL,
    LevelType.LOW_GAMMA,
}

RESISTANCE_TYPES = {
    LevelType.CALL_WALL,
    LevelType.VAH,
    LevelType.OVH,
    LevelType.HIGH_GAMMA,
}


def generate_level_scenarios(
    state: MarketState,
    levels: Iterable[MarketLevel],
    *,
    max_scenarios: int = 5,
) -> tuple[Scenario, ...]:
    """Generate deterministic, conditional scenarios from current market state.

    Scenarios describe structural conditions around existing levels. They do
    not predict outcomes and do not attach probabilities.
    """
    if max_scenarios <= 0:
        return ()

    ordered_levels = _rank_levels(tuple(levels), state.spot)
    scenarios: list[Scenario] = []

    if state.major_gamma_level is not None:
        scenarios.extend(_major_gamma_scenarios(state, ordered_levels))

    if state.nearest_resistance is not None:
        scenarios.append(_resistance_scenario(state, ordered_levels))

    if state.nearest_support is not None:
        scenarios.append(_support_scenario(state, ordered_levels))

    if not scenarios and ordered_levels:
        scenarios.append(_level_interaction_scenario(state, ordered_levels[0], ordered_levels))

    return tuple(_dedupe_scenarios(scenarios)[:max_scenarios])


def _major_gamma_scenarios(state: MarketState, levels: tuple[MarketLevel, ...]) -> list[Scenario]:
    major = state.major_gamma_level
    if major is None:
        return []

    upside_levels = _levels_above(levels, state.spot, exclude_id=major.id, limit=2)
    downside_levels = _levels_below(levels, state.spot, exclude_id=major.id, limit=2)

    holds_direction = (
        ScenarioDirection.RANGE
        if state.structure is MarketStructure.AT_MAJOR_GAMMA
        else ScenarioDirection.UPSIDE
    )
    holds_title = (
        f"Price holds above {major.price:g}"
        if state.spot >= major.price
        else f"Price reclaims {major.price:g}"
    )
    loses_title = (
        f"Price loses {major.price:g}"
        if state.spot >= major.price
        else f"Price remains below {major.price:g}"
    )

    return [
        Scenario(
            id=f"{state.symbol}-HOLD-MAJOR-GAMMA-{major.price:g}",
            title=holds_title,
            direction=holds_direction,
            trigger=f"Sustained trade above {major.price:g}",
            key_level=major,
            conditions=(
                f"Spot holds above the {major.level_type.value} at {major.price:g}.",
                f"Gamma regime remains {state.gamma_regime.value}.",
                "No stronger lower level replaces the current major gamma area.",
            ),
            structural_implication=(
                "Upper positioning levels remain the next structural reference while price is "
                "accepted above the major gamma area."
            ),
            invalidation=f"Sustained trade below {major.price:g}.",
            next_levels=upside_levels,
            supporting_data=_supporting_data(state, major),
        ),
        Scenario(
            id=f"{state.symbol}-LOSE-MAJOR-GAMMA-{major.price:g}",
            title=loses_title,
            direction=ScenarioDirection.DOWNSIDE,
            trigger=f"Sustained trade below {major.price:g}",
            key_level=major,
            conditions=(
                f"Spot moves below the {major.level_type.value} at {major.price:g}.",
                "Downside levels become more relevant if acceptance below the level persists.",
                f"Current structure is {state.structure.value}.",
            ),
            structural_implication=(
                "Lower positioning levels become the next structural reference while price is "
                "accepted below the major gamma area."
            ),
            invalidation=f"Recovery above {major.price:g}.",
            next_levels=downside_levels,
            supporting_data=_supporting_data(state, major),
        ),
    ]


def _resistance_scenario(state: MarketState, levels: tuple[MarketLevel, ...]) -> Scenario:
    resistance = state.nearest_resistance
    assert resistance is not None
    return Scenario(
        id=f"{state.symbol}-TEST-RESISTANCE-{resistance.price:g}",
        title=f"Price tests {resistance.price:g} resistance",
        direction=ScenarioDirection.UPSIDE,
        trigger=f"Trade into {resistance.level_type.value} at {resistance.price:g}",
        key_level=resistance,
        conditions=(
            f"Spot continues toward nearest resistance at {resistance.price:g}.",
            "The level remains active and keeps its relative strength.",
        ),
        structural_implication=(
            "Acceptance above resistance shifts attention to the next upper level; rejection keeps "
            "the current range structure in focus."
        ),
        invalidation=f"Failure to hold above nearby support at {_price_or_na(state.nearest_support)}.",
        next_levels=_levels_above(levels, resistance.price, exclude_id=resistance.id, limit=2),
        supporting_data=_supporting_data(state, resistance),
    )


def _support_scenario(state: MarketState, levels: tuple[MarketLevel, ...]) -> Scenario:
    support = state.nearest_support
    assert support is not None
    return Scenario(
        id=f"{state.symbol}-TEST-SUPPORT-{support.price:g}",
        title=f"Price tests {support.price:g} support",
        direction=ScenarioDirection.DOWNSIDE,
        trigger=f"Trade into {support.level_type.value} at {support.price:g}",
        key_level=support,
        conditions=(
            f"Spot continues toward nearest support at {support.price:g}.",
            "The level remains active and keeps its relative strength.",
        ),
        structural_implication=(
            "Acceptance below support shifts attention to the next lower level; recovery keeps "
            "the current range structure in focus."
        ),
        invalidation=f"Recovery above nearby resistance at {_price_or_na(state.nearest_resistance)}.",
        next_levels=_levels_below(levels, support.price, exclude_id=support.id, limit=2),
        supporting_data=_supporting_data(state, support),
    )


def _level_interaction_scenario(
    state: MarketState,
    level: MarketLevel,
    levels: tuple[MarketLevel, ...],
) -> Scenario:
    direction = ScenarioDirection.DOWNSIDE if level.price < state.spot else ScenarioDirection.UPSIDE
    next_levels = (
        _levels_below(levels, level.price, exclude_id=level.id, limit=2)
        if direction is ScenarioDirection.DOWNSIDE
        else _levels_above(levels, level.price, exclude_id=level.id, limit=2)
    )
    return Scenario(
        id=f"{state.symbol}-INTERACTION-{level.price:g}",
        title=f"Price interacts with {level.price:g}",
        direction=direction,
        trigger=f"Price approaches {level.level_type.value} at {level.price:g}",
        key_level=level,
        conditions=("The level remains among the strongest nearby references.",),
        structural_implication="The level is a nearby structural reference until stronger data replaces it.",
        invalidation=f"Price moves away from {level.price:g} and a nearer level becomes dominant.",
        next_levels=next_levels,
        supporting_data=_supporting_data(state, level),
    )


def _rank_levels(levels: tuple[MarketLevel, ...], spot: float) -> tuple[MarketLevel, ...]:
    return tuple(
        sorted(
            levels,
            key=lambda level: (
                abs(level.price - spot),
                -level.strength,
                level.price,
            ),
        )
    )


def _levels_above(
    levels: tuple[MarketLevel, ...],
    price: float,
    *,
    exclude_id: str,
    limit: int,
) -> tuple[MarketLevel, ...]:
    candidates = [
        level for level in levels
        if level.id != exclude_id and level.price > price
    ]
    return tuple(sorted(candidates, key=lambda level: (level.price, -level.strength))[:limit])


def _levels_below(
    levels: tuple[MarketLevel, ...],
    price: float,
    *,
    exclude_id: str,
    limit: int,
) -> tuple[MarketLevel, ...]:
    candidates = [
        level for level in levels
        if level.id != exclude_id and level.price < price
    ]
    return tuple(sorted(candidates, key=lambda level: (-level.price, -level.strength))[:limit])


def _dedupe_scenarios(scenarios: list[Scenario]) -> list[Scenario]:
    seen: set[str] = set()
    unique: list[Scenario] = []
    for scenario in scenarios:
        if scenario.id in seen:
            continue
        seen.add(scenario.id)
        unique.append(scenario)
    return unique


def _supporting_data(state: MarketState, level: MarketLevel) -> dict[str, object]:
    return {
        "spot": state.spot,
        "gamma_regime": state.gamma_regime.value,
        "market_structure": state.structure.value,
        "level_type": level.level_type.value,
        "level_strength": level.strength,
        "level_status": level.status.value,
        "distance_percent": level.distance_percent,
    }


def _price_or_na(level: MarketLevel | None) -> str:
    if level is None:
        return "N/A"
    return f"{level.price:g}"
