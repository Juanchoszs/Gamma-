from __future__ import annotations

from datetime import datetime

import pytest

from gex.domain.market.intelligence import (
    GammaRegime,
    LevelSource,
    LevelStatus,
    LevelType,
    MarketLevel,
    MarketStructure,
    SessionType,
)
from gex.domain.market.state import build_market_state, classify_gamma_regime


def _level(level_type: LevelType, price: float, strength: int, gamma: float | None = None) -> MarketLevel:
    return MarketLevel(
        id=f"SPX-{level_type.value}-{price:g}",
        level_type=level_type,
        price=price,
        source=LevelSource.GEX_ENGINE if level_type is LevelType.GEX_WALL else LevelSource.OPTIONS_CHAIN,
        timestamp=datetime(2026, 9, 18, 9, 42),
        strength=strength,
        gamma=gamma,
        session=SessionType.REGULAR,
    )


def test_gamma_regime_classification_is_deterministic():
    assert classify_gamma_regime(1.0) is GammaRegime.POSITIVE_GAMMA
    assert classify_gamma_regime(-1.0) is GammaRegime.NEGATIVE_GAMMA
    assert classify_gamma_regime(0.0) is GammaRegime.NEUTRAL_GAMMA
    assert classify_gamma_regime(None) is GammaRegime.UNKNOWN
    assert classify_gamma_regime(0.5, neutral_threshold=1.0) is GammaRegime.NEUTRAL_GAMMA


def test_build_market_state_selects_nearest_levels_and_major_gamma():
    timestamp = datetime(2026, 9, 18, 9, 45)
    state = build_market_state(
        symbol="SPX",
        spot=7592.45,
        timestamp=timestamp,
        levels=[
            _level(LevelType.PUT_WALL, 7580.0, 82, gamma=-2_000_000),
            _level(LevelType.GEX_WALL, 7590.0, 88, gamma=5_000_000),
            _level(LevelType.CALL_WALL, 7600.0, 87, gamma=1_000_000),
        ],
        net_gex=12_500_000,
        session=SessionType.REGULAR,
        data_status="LIVE",
    )

    assert state.gamma_regime is GammaRegime.POSITIVE_GAMMA
    assert state.structure is MarketStructure.AT_MAJOR_GAMMA
    assert state.major_gamma_level is not None
    assert state.major_gamma_level.status is LevelStatus.TESTING
    assert state.nearest_support is not None
    assert state.nearest_support.price == 7590.0
    assert state.nearest_resistance is not None
    assert state.nearest_resistance.price == 7600.0
    assert state.data_status == "LIVE"
    assert any("Major gamma level" in reason for reason in state.reasons)


def test_build_market_state_classifies_above_and_below_major_gamma():
    timestamp = datetime(2026, 9, 18, 9, 45)
    levels = [_level(LevelType.GEX_WALL, 7590.0, 88, gamma=5_000_000)]

    above = build_market_state(symbol="SPX", spot=7615.0, timestamp=timestamp, levels=levels)
    below = build_market_state(symbol="SPX", spot=7565.0, timestamp=timestamp, levels=levels)

    assert above.structure is MarketStructure.ABOVE_MAJOR_GAMMA
    assert below.structure is MarketStructure.BELOW_MAJOR_GAMMA


def test_build_market_state_rejects_invalid_inputs():
    with pytest.raises(ValueError, match="spot"):
        build_market_state(symbol="SPX", spot=0, timestamp=datetime(2026, 9, 18), levels=[])
    with pytest.raises(ValueError, match="threshold"):
        classify_gamma_regime(1.0, neutral_threshold=-1.0)
