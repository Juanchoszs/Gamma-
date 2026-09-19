from __future__ import annotations

from datetime import datetime

from gex.application.market_intelligence import (
    build_market_intelligence_snapshot,
    market_level_to_dict,
    snapshot_to_dict,
)
from gex.domain.market.intelligence import (
    LevelSource,
    LevelStatus,
    LevelType,
    MarketLevel,
    SessionType,
)


def _level(
    level_type: LevelType,
    price: float,
    strength: int,
    *,
    gamma: float | None = None,
    volume: float | None = None,
    open_interest: float | None = None,
) -> MarketLevel:
    source = LevelSource.GEX_ENGINE if level_type is LevelType.GEX_WALL else LevelSource.OPTIONS_CHAIN
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


def _snapshot():
    return build_market_intelligence_snapshot(
        symbol="SPX",
        spot=7592.45,
        timestamp=datetime(2026, 9, 18, 9, 45),
        levels=(
            _level(LevelType.PUT_WALL, 7580.0, 82, gamma=-2_000_000, open_interest=42_100),
            _level(LevelType.GEX_WALL, 7590.0, 88, gamma=5_000_000, volume=8_200),
            _level(LevelType.CALL_WALL, 7600.0, 87, gamma=1_000_000, volume=15_420),
        ),
        net_gex=12_500_000,
        session=SessionType.REGULAR,
        data_status="LIVE",
    )


def test_snapshot_to_dict_exposes_api_ready_market_intelligence_sections():
    payload = snapshot_to_dict(_snapshot())

    assert sorted(payload) == ["report", "scenarios", "state"]
    assert payload["state"]["symbol"] == "SPX"
    assert payload["state"]["timestamp"] == "2026-09-18T09:45:00"
    assert payload["state"]["spot"] == 7592.45
    assert payload["state"]["gamma_regime"] == "POSITIVE_GAMMA"
    assert payload["state"]["data_status"] == "LIVE"
    assert payload["state"]["major_gamma_level"]["status"] == "TESTING"
    assert payload["scenarios"][0]["title"] == "Price holds above 7590"
    assert payload["report"]["market_state"]["structure"] == "AT_MAJOR_GAMMA"
    assert payload["report"]["key_levels"][0]["status"] == "TESTING"


def test_snapshot_payload_contains_report_summaries_and_scenario_context():
    payload = snapshot_to_dict(_snapshot())
    scenario = payload["scenarios"][0]

    assert payload["report"]["positioning_summary"]
    assert payload["report"]["structure_summary"]
    assert scenario["trigger"] == "Sustained trade above 7590"
    assert scenario["conditions"]
    assert scenario["invalidation"] == "Sustained trade below 7590."
    assert scenario["supporting_data"]["gamma_regime"] == "POSITIVE_GAMMA"
    assert scenario["key_level"]["type"] == "GEX_WALL"


def test_level_serializer_omits_missing_optional_fields():
    payload = market_level_to_dict(
        MarketLevel(
            id="SPX-CALL_WALL-7600",
            level_type=LevelType.CALL_WALL,
            price=7600.0,
            source=LevelSource.OPTIONS_CHAIN,
            timestamp=datetime(2026, 9, 18, 9, 42),
            strength=87,
            session=SessionType.REGULAR,
            status=LevelStatus.ACTIVE,
        )
    )

    assert payload["type"] == "CALL_WALL"
    assert "gamma" not in payload
    assert "open_interest" not in payload
    assert "metadata" not in payload


def test_snapshot_payload_does_not_add_probability_or_confidence_fields():
    payload = snapshot_to_dict(_snapshot())
    text = repr(payload).lower()

    assert "probability" not in text
    assert "confidence" not in text
    assert "reaction_probability" not in text
