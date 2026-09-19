"""Deterministic price/level interaction rules for market intelligence."""
from __future__ import annotations

from dataclasses import replace

from gex.domain.market.intelligence import LevelStatus, MarketLevel


def distance_percent(spot: float, level_price: float) -> float:
    """Return spot distance from a level as a signed percent of level price."""
    if spot <= 0:
        raise ValueError("spot must be positive")
    if level_price <= 0:
        raise ValueError("level price must be positive")
    return ((float(spot) - float(level_price)) / float(level_price)) * 100.0


def classify_level_interaction(
    spot: float,
    level_price: float,
    *,
    previous_spot: float | None = None,
    test_tolerance_pct: float = 0.05,
    approach_tolerance_pct: float = 0.30,
) -> LevelStatus:
    """Classify how price is interacting with a level.

    Tolerances are deterministic percent distances, not probabilities. A
    previous spot allows the engine to distinguish reclaim/break transitions.
    """
    if test_tolerance_pct < 0 or approach_tolerance_pct < 0:
        raise ValueError("interaction tolerances must be non-negative")
    if approach_tolerance_pct < test_tolerance_pct:
        raise ValueError("approach tolerance must be greater than or equal to test tolerance")

    current_distance = distance_percent(spot, level_price)
    abs_distance = abs(current_distance)
    if abs_distance <= test_tolerance_pct:
        return LevelStatus.TESTING

    if previous_spot is not None:
        previous_distance = distance_percent(previous_spot, level_price)
        crossed_up = previous_distance < -test_tolerance_pct and current_distance > test_tolerance_pct
        crossed_down = previous_distance > test_tolerance_pct and current_distance < -test_tolerance_pct
        if crossed_up:
            return LevelStatus.RECLAIMED
        if crossed_down:
            return LevelStatus.BROKEN

    if abs_distance <= approach_tolerance_pct:
        return LevelStatus.APPROACHING
    if current_distance > 0:
        return LevelStatus.ABOVE_LEVEL
    return LevelStatus.BELOW_LEVEL


def update_level_interaction(
    level: MarketLevel,
    spot: float,
    *,
    previous_spot: float | None = None,
    test_tolerance_pct: float = 0.05,
    approach_tolerance_pct: float = 0.30,
) -> MarketLevel:
    """Return a copy of a market level with current distance and status."""
    status = classify_level_interaction(
        spot,
        level.price,
        previous_spot=previous_spot,
        test_tolerance_pct=test_tolerance_pct,
        approach_tolerance_pct=approach_tolerance_pct,
    )
    return replace(
        level,
        distance_percent=distance_percent(spot, level.price),
        status=status,
    )
