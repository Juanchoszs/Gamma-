from __future__ import annotations

from datetime import datetime

from gex.domain.market.intelligence import (
    GammaRegime,
    LevelSource,
    LevelStatus,
    LevelType,
    MarketLevel,
    MarketStructure,
    SessionType,
)
from gex.domain.market.scenarios import generate_level_scenarios
from gex.domain.market.state import build_market_state


def _level(level_type: LevelType, price: float, strength: int) -> MarketLevel:
    source = LevelSource.GEX_ENGINE if level_type is LevelType.GEX_WALL else LevelSource.OPTIONS_CHAIN
    return MarketLevel(
        id=f"SPX-{level_type.value}-{price:g}",
        level_type=level_type,
        price=price,
        source=source,
        timestamp=datetime(2026, 9, 18, 9, 42),
        strength=strength,
        gamma=5_000_000 if level_type is LevelType.GEX_WALL else None,
        session=SessionType.REGULAR,
        status=LevelStatus.ACTIVE,
    )


def _state_and_levels(spot: float = 7592.45):
    levels = (
        _level(LevelType.PUT_WALL, 7580.0, 82),
        _level(LevelType.GEX_WALL, 7590.0, 88),
        _level(LevelType.CALL_WALL, 7600.0, 87),
        _level(LevelType.HIGH_GAMMA, 7610.0, 78),
        _level(LevelType.LOW_GAMMA, 7570.0, 74),
    )
    state = build_market_state(
        symbol="SPX",
        spot=spot,
        timestamp=datetime(2026, 9, 18, 9, 45),
        levels=levels,
        net_gex=12_500_000,
        session=SessionType.REGULAR,
        data_status="LIVE",
    )
    return state, levels


def test_scenario_engine_generates_conditional_major_gamma_scenarios():
    state, levels = _state_and_levels()

    scenarios = generate_level_scenarios(state, levels)

    assert len(scenarios) >= 2
    hold = scenarios[0]
    lose = scenarios[1]
    assert hold.title == "Price holds above 7590"
    assert hold.key_level is not None
    assert hold.key_level.level_type is LevelType.GEX_WALL
    assert "Sustained trade above 7590" == hold.trigger
    assert hold.invalidation == "Sustained trade below 7590."
    assert any("Spot holds" in condition for condition in hold.conditions)
    assert "accepted above" in hold.structural_implication
    assert hold.next_levels[0].price == 7600.0
    assert lose.invalidation == "Recovery above 7590."
    assert lose.next_levels[0].price == 7580.0


def test_scenarios_do_not_expose_confidence_or_probability_fields():
    state, levels = _state_and_levels()

    scenario = generate_level_scenarios(state, levels)[0]

    assert "confidence" not in scenario.__dataclass_fields__
    assert "probability" not in scenario.__dataclass_fields__
    assert "probability" not in scenario.supporting_data


def test_support_and_resistance_scenarios_include_next_levels():
    state, levels = _state_and_levels()

    scenarios = generate_level_scenarios(state, levels, max_scenarios=5)
    resistance = next(s for s in scenarios if s.id == "SPX-TEST-RESISTANCE-7600")
    support = next(s for s in scenarios if s.id == "SPX-TEST-SUPPORT-7590")

    assert resistance.next_levels[0].price == 7610.0
    assert resistance.invalidation == "Failure to hold above nearby support at 7590."
    assert support.next_levels[0].price == 7580.0
    assert support.invalidation == "Recovery above nearby resistance at 7600."


def test_scenario_engine_handles_below_major_gamma_structure():
    state, levels = _state_and_levels(spot=7565.0)

    scenarios = generate_level_scenarios(state, levels, max_scenarios=2)

    assert state.gamma_regime is GammaRegime.POSITIVE_GAMMA
    assert state.structure is MarketStructure.BELOW_MAJOR_GAMMA
    assert scenarios[0].title == "Price reclaims 7590"
    assert scenarios[1].title == "Price remains below 7590"
    assert scenarios[1].next_levels == ()


def test_scenario_limit_and_empty_inputs_are_deterministic():
    state, levels = _state_and_levels()

    assert len(generate_level_scenarios(state, levels, max_scenarios=1)) == 1
    assert generate_level_scenarios(state, levels, max_scenarios=0) == ()
