from __future__ import annotations

from datetime import datetime

from gex.domain.market.intelligence import (
    LevelSource,
    LevelStatus,
    LevelType,
    MarketLevel,
    SessionType,
)
from gex.domain.market.reports import build_market_report
from gex.domain.market.state import build_market_state


def _level(
    level_type: LevelType,
    price: float,
    strength: int,
    *,
    volume: float | None = None,
    open_interest: float | None = None,
    gamma: float | None = None,
) -> MarketLevel:
    source = LevelSource.GEX_ENGINE if level_type in {LevelType.GEX_WALL, LevelType.GAMMA_FLIP} else LevelSource.OPTIONS_CHAIN
    return MarketLevel(
        id=f"SPX-{level_type.value}-{price:g}",
        level_type=level_type,
        price=price,
        source=source,
        timestamp=datetime(2026, 9, 18, 9, 42),
        strength=strength,
        volume=volume,
        open_interest=open_interest,
        gamma=gamma,
        session=SessionType.REGULAR,
        status=LevelStatus.ACTIVE,
    )


def _state_and_levels():
    levels = (
        _level(LevelType.PUT_WALL, 7580.0, 82, volume=12_400, open_interest=42_100, gamma=-2_000_000),
        _level(LevelType.GEX_WALL, 7590.0, 88, volume=8_200, open_interest=35_000, gamma=5_000_000),
        _level(LevelType.CALL_WALL, 7600.0, 87, volume=15_420, open_interest=38_000, gamma=1_000_000),
        _level(LevelType.HIGH_GAMMA, 7610.0, 78, volume=4_200, open_interest=19_100, gamma=3_000_000),
        _level(LevelType.POC, 7588.0, 70, volume=18_500, open_interest=None),
        _level(LevelType.KEY_STRIKE, 7625.0, 91, volume=100, open_interest=100),
    )
    state = build_market_state(
        symbol="SPX",
        spot=7592.45,
        timestamp=datetime(2026, 9, 18, 9, 45),
        levels=levels,
        net_gex=12_500_000,
        session=SessionType.REGULAR,
        data_status="LIVE",
    )
    return state, levels


def test_market_report_builds_snapshot_from_state_levels_and_scenarios():
    state, levels = _state_and_levels()

    report = build_market_report(state, levels)

    assert report.symbol == "SPX"
    assert report.timestamp == state.timestamp
    assert report.market_state is state
    assert report.key_levels[0].id == state.nearest_support.id
    assert report.key_levels[1].id == state.nearest_resistance.id
    assert report.scenarios
    assert report.scenarios[0].title == "Price holds above 7590"


def test_market_report_summarizes_positioning_and_structure():
    state, levels = _state_and_levels()

    report = build_market_report(state, levels)

    assert any("Call concentration: CALL_WALL at 7600" in item for item in report.positioning_summary)
    assert any("Put concentration: PUT_WALL at 7580" in item for item in report.positioning_summary)
    assert any("Gamma concentration: GEX_WALL at 7590" in item for item in report.positioning_summary)
    assert any("Major OI reference is PUT_WALL at 7580" in item for item in report.positioning_summary)
    assert any("Major volume reference is POC at 7588" in item for item in report.positioning_summary)
    assert any("Spot 7592.45 is classified as AT_MAJOR_GAMMA" in item for item in report.structure_summary)
    assert any("Price is TESTING GEX_WALL at 7590" in item for item in report.structure_summary)
    assert any("Active scenario:" in item for item in report.structure_summary)


def test_market_report_ranking_uses_relevant_levels_not_arbitrary_strength():
    state, levels = _state_and_levels()

    report = build_market_report(state, levels, max_levels=3)

    assert [level.level_type for level in report.key_levels] == [
        LevelType.GEX_WALL,
        LevelType.CALL_WALL,
        LevelType.POC,
    ]
    assert all(level.level_type is not LevelType.KEY_STRIKE for level in report.key_levels)


def test_market_report_keeps_volume_and_oi_nodes_for_market_map_context():
    state, levels = _state_and_levels()
    levels = levels + (
        _level(LevelType.VOLUME_NODE, 7595.0, 76, volume=50_000),
        _level(LevelType.OI_NODE, 7585.0, 74, open_interest=90_000),
    )

    report = build_market_report(state, levels)

    assert LevelType.VOLUME_NODE in {level.level_type for level in report.key_levels}
    assert LevelType.OI_NODE in {level.level_type for level in report.key_levels}


def test_market_report_does_not_create_fake_probability_language():
    state, levels = _state_and_levels()

    report = build_market_report(state, levels)
    text = " ".join((*report.positioning_summary, *report.structure_summary))

    assert "probability" not in report.__dataclass_fields__
    assert "confidence" not in report.__dataclass_fields__
    assert "probability" not in text.lower()
    assert "guaranteed" not in text.lower()


def test_market_report_accepts_prebuilt_scenarios_and_limits_output():
    state, levels = _state_and_levels()
    generated = build_market_report(state, levels).scenarios

    report = build_market_report(state, levels, scenarios=generated, max_scenarios=1)

    assert len(report.scenarios) == 1
    assert report.scenarios[0] is generated[0]
