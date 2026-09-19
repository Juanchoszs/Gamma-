from __future__ import annotations

from datetime import datetime

import pytest

from gex.domain.market.intelligence import (
    GammaRegime,
    LevelSource,
    LevelStatus,
    LevelType,
    MarketLevel,
    MarketReport,
    MarketState,
    MarketStructure,
    Scenario,
    ScenarioDirection,
    SessionType,
)


def test_market_level_is_a_deterministic_score_not_probability():
    level = MarketLevel(
        id="SPX-20260918-CALL_WALL-7600",
        level_type=LevelType.CALL_WALL,
        price=7600.0,
        source=LevelSource.OPTIONS_CHAIN,
        timestamp=datetime(2026, 9, 18, 9, 42),
        strength=87,
        distance_percent=0.32,
        open_interest=42_100,
        volume=15_420,
        gamma=1_250_000.0,
        session=SessionType.REGULAR,
        status=LevelStatus.ACTIVE,
    )

    assert level.strength == 87
    assert level.level_type is LevelType.CALL_WALL
    assert "probability" not in level.__dataclass_fields__


def test_market_level_rejects_invalid_strength_and_price():
    kwargs = {
        "id": "bad",
        "level_type": LevelType.PUT_WALL,
        "price": 7580.0,
        "source": LevelSource.OPTIONS_CHAIN,
        "timestamp": datetime(2026, 9, 18, 9, 42),
        "strength": 101,
    }

    with pytest.raises(ValueError, match="strength"):
        MarketLevel(**kwargs)

    with pytest.raises(ValueError, match="price"):
        MarketLevel(**{**kwargs, "price": 0, "strength": 50})


def test_market_state_scenario_and_report_compose_without_fake_certainty():
    timestamp = datetime(2026, 9, 18, 9, 42)
    support = MarketLevel(
        id="SPX-20260918-PUT_WALL-7580",
        level_type=LevelType.PUT_WALL,
        price=7580.0,
        source=LevelSource.OPTIONS_CHAIN,
        timestamp=timestamp,
        strength=82,
        session=SessionType.REGULAR,
        status=LevelStatus.ACTIVE,
    )
    resistance = MarketLevel(
        id="SPX-20260918-CALL_WALL-7600",
        level_type=LevelType.CALL_WALL,
        price=7600.0,
        source=LevelSource.OPTIONS_CHAIN,
        timestamp=timestamp,
        strength=87,
        session=SessionType.REGULAR,
        status=LevelStatus.ACTIVE,
    )
    state = MarketState(
        symbol="SPX",
        timestamp=timestamp,
        spot=7592.45,
        gamma_regime=GammaRegime.POSITIVE_GAMMA,
        structure=MarketStructure.RANGE,
        session=SessionType.REGULAR,
        nearest_support=support,
        nearest_resistance=resistance,
        data_status="LIVE",
        reasons=("Net gamma is positive", "Spot is between nearest walls"),
    )
    scenario = Scenario(
        id="SPX-HOLDS-7590",
        title="Price holds above major gamma area",
        direction=ScenarioDirection.UPSIDE,
        trigger="Sustained trade above 7590",
        key_level=resistance,
        conditions=("Spot remains above 7590",),
        structural_implication="Upper positioning zones remain relevant.",
        invalidation="Sustained trade below 7590",
        next_levels=(resistance,),
    )
    report = MarketReport(
        symbol="SPX",
        timestamp=timestamp,
        market_state=state,
        key_levels=(support, resistance),
        scenarios=(scenario,),
    )

    assert report.market_state.gamma_regime is GammaRegime.POSITIVE_GAMMA
    assert report.scenarios[0].invalidation
    assert "confidence" not in report.scenarios[0].__dataclass_fields__
