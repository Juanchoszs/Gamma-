from __future__ import annotations

from datetime import datetime

import pytest

from gex.application.market_intelligence import (
    MarketIntelligenceConfig,
    build_market_intelligence_snapshot,
)
from gex.domain.market.intelligence import (
    GammaRegime,
    LevelSource,
    LevelStatus,
    LevelType,
    MarketStructure,
    MarketLevel,
    SessionType,
)


def _level(
    level_type: LevelType,
    price: float,
    strength: int,
    *,
    gamma: float | None = None,
) -> MarketLevel:
    source = LevelSource.GEX_ENGINE if level_type is LevelType.GEX_WALL else LevelSource.OPTIONS_CHAIN
    return MarketLevel(
        id=f"SPX-{level_type.value}-{price:g}",
        level_type=level_type,
        price=price,
        source=source,
        timestamp=datetime(2026, 9, 18, 9, 42),
        strength=strength,
        gamma=gamma,
        session=SessionType.REGULAR,
        status=LevelStatus.ACTIVE,
    )


def _levels() -> tuple[MarketLevel, ...]:
    return (
        _level(LevelType.PUT_WALL, 7580.0, 82, gamma=-2_000_000),
        _level(LevelType.GEX_WALL, 7590.0, 88, gamma=5_000_000),
        _level(LevelType.CALL_WALL, 7600.0, 87, gamma=1_000_000),
        _level(LevelType.HIGH_GAMMA, 7610.0, 78, gamma=3_000_000),
    )


def test_market_intelligence_service_builds_state_scenarios_and_report():
    snapshot = build_market_intelligence_snapshot(
        symbol="SPX",
        spot=7592.45,
        timestamp=datetime(2026, 9, 18, 9, 45),
        levels=_levels(),
        net_gex=12_500_000,
        session=SessionType.REGULAR,
        data_status="LIVE",
        implied_volatility=0.20,
        call_open_interest=100_000,
        put_open_interest=75_000,
    )

    assert snapshot.state.gamma_regime is GammaRegime.POSITIVE_GAMMA
    assert snapshot.state.structure is MarketStructure.AT_MAJOR_GAMMA
    assert snapshot.state.data_status == "LIVE"
    assert snapshot.state.implied_volatility == 0.20
    assert snapshot.state.positioning == "CALL_HEAVY"
    assert snapshot.scenarios
    assert snapshot.scenarios[0].title == "Price holds above 7590"
    assert snapshot.report.market_state is snapshot.state
    assert snapshot.report.scenarios == snapshot.scenarios
    assert snapshot.report.key_levels[0].status is LevelStatus.TESTING
    assert all(level.status is not LevelStatus.UNKNOWN for level in snapshot.levels)


def test_market_intelligence_service_respects_limits_and_neutral_threshold():
    snapshot = build_market_intelligence_snapshot(
        symbol="SPX",
        spot=7592.45,
        timestamp=datetime(2026, 9, 18, 9, 45),
        levels=_levels(),
        net_gex=0.5,
        session=SessionType.REGULAR,
        config=MarketIntelligenceConfig(
            max_scenarios=1,
            max_report_levels=2,
            neutral_gex_threshold=1.0,
        ),
    )

    assert snapshot.state.gamma_regime is GammaRegime.NEUTRAL_GAMMA
    assert len(snapshot.scenarios) == 1
    assert len(snapshot.report.key_levels) == 2


def test_market_intelligence_service_uses_previous_spot_for_crossing_status():
    snapshot = build_market_intelligence_snapshot(
        symbol="SPX",
        spot=7602.0,
        previous_spot=7580.0,
        timestamp=datetime(2026, 9, 18, 9, 45),
        levels=_levels()[:3],
        net_gex=12_500_000,
        session=SessionType.REGULAR,
    )

    assert snapshot.state.major_gamma_level is not None
    assert snapshot.state.major_gamma_level.status is LevelStatus.RECLAIMED
    assert any("RECLAIMED GEX_WALL" in item for item in snapshot.report.structure_summary)


def test_market_intelligence_service_config_rejects_invalid_values():
    with pytest.raises(ValueError, match="max_scenarios"):
        MarketIntelligenceConfig(max_scenarios=-1)
    with pytest.raises(ValueError, match="max_report_levels"):
        MarketIntelligenceConfig(max_report_levels=-1)
    with pytest.raises(ValueError, match="neutral_gex_threshold"):
        MarketIntelligenceConfig(neutral_gex_threshold=-1.0)
