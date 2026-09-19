from __future__ import annotations

from datetime import datetime

import pytest

from gex.domain.market.intelligence import LevelSource, LevelStatus, LevelType, MarketLevel
from gex.domain.market.interaction import (
    classify_level_interaction,
    distance_percent,
    update_level_interaction,
)


def _level(price: float = 7590.0) -> MarketLevel:
    return MarketLevel(
        id="SPX-GEX_WALL-7590",
        level_type=LevelType.GEX_WALL,
        price=price,
        source=LevelSource.GEX_ENGINE,
        timestamp=datetime(2026, 9, 18, 9, 42),
        strength=88,
    )


def test_distance_percent_is_signed_from_level_price():
    assert round(distance_percent(7597.59, 7590.0), 4) == 0.1
    assert round(distance_percent(7582.41, 7590.0), 4) == -0.1


def test_level_interaction_classifies_testing_and_distance():
    updated = update_level_interaction(_level(), 7591.0, test_tolerance_pct=0.05)

    assert updated.status is LevelStatus.TESTING
    assert updated.distance_percent is not None
    assert updated.distance_percent > 0


def test_level_interaction_classifies_above_below_and_approaching():
    assert classify_level_interaction(7588.0, 7590.0, test_tolerance_pct=0.01) is LevelStatus.APPROACHING
    assert classify_level_interaction(7615.0, 7590.0, approach_tolerance_pct=0.10) is LevelStatus.ABOVE_LEVEL
    assert classify_level_interaction(7565.0, 7590.0, approach_tolerance_pct=0.10) is LevelStatus.BELOW_LEVEL


def test_level_interaction_detects_reclaim_and_break_transitions():
    assert classify_level_interaction(
        7600.0,
        7590.0,
        previous_spot=7580.0,
        test_tolerance_pct=0.05,
    ) is LevelStatus.RECLAIMED
    assert classify_level_interaction(
        7580.0,
        7590.0,
        previous_spot=7600.0,
        test_tolerance_pct=0.05,
    ) is LevelStatus.BROKEN


def test_level_interaction_rejects_invalid_inputs():
    with pytest.raises(ValueError, match="spot"):
        distance_percent(0, 7590.0)
    with pytest.raises(ValueError, match="tolerances"):
        classify_level_interaction(7590.0, 7590.0, test_tolerance_pct=-1)
    with pytest.raises(ValueError, match="approach"):
        classify_level_interaction(7590.0, 7590.0, test_tolerance_pct=0.2, approach_tolerance_pct=0.1)
