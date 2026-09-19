from __future__ import annotations

from datetime import datetime

from gex.application.market_intelligence.level_inspector import build_level_inspector_payload
from gex.domain.market.intelligence import (
    LevelSource,
    LevelStatus,
    LevelType,
    MarketLevel,
    Scenario,
    ScenarioDirection,
    SessionType,
)


def _level(
    level_id: str,
    price: float,
    level_type: LevelType = LevelType.GEX_WALL,
) -> MarketLevel:
    return MarketLevel(
        id=level_id,
        level_type=level_type,
        price=price,
        source=LevelSource.GEX_ENGINE,
        timestamp=datetime(2026, 9, 18, 9, 45),
        strength=82,
        distance_percent=0.04,
        volume=12_000.0,
        open_interest=44_000.0,
        gamma=2_500_000.0,
        session=SessionType.REGULAR,
        status=LevelStatus.TESTING,
        metadata={"side": "C"},
    )


def test_level_inspector_payload_contains_metrics_context_and_methodology():
    selected = _level("GEX_WALL-7600", 7600.0)
    below = _level("PUT_WALL-7580", 7580.0, LevelType.PUT_WALL)
    above = _level("CALL_WALL-7620", 7620.0, LevelType.CALL_WALL)
    scenario = Scenario(
        id="SPX-HOLD-MAJOR-GAMMA-7600",
        title="Price holds above 7600",
        direction=ScenarioDirection.UPSIDE,
        trigger="Sustained trade above 7600",
        key_level=selected,
        conditions=("Spot holds the level.",),
        structural_implication="Upper levels remain in focus.",
        invalidation="Sustained trade below 7600.",
    )

    payload = build_level_inspector_payload(
        level=selected,
        spot=7598.0,
        related_levels=(below, selected, above),
        scenarios=(scenario,),
    )

    assert payload["level"]["id"] == "GEX_WALL-7600"
    assert payload["summary"]["status"] == "TESTING"
    assert payload["metrics"]["open_interest"] == 44_000.0
    assert payload["metrics"]["volume"] == 12_000.0
    assert payload["metrics"]["gamma"] == 2_500_000.0
    assert payload["metrics"]["metadata"] == {"side": "C"}
    assert payload["context"]["spot"] == 7598.0
    assert payload["context"]["position"] == "ABOVE_SPOT"
    assert payload["context"]["nearest_below"]["id"] == "PUT_WALL-7580"
    assert payload["context"]["nearest_above"]["id"] == "CALL_WALL-7620"
    assert payload["context"]["related_scenarios"][0]["relationship"] == "KEY_LEVEL"
    assert payload["methodology"]["strength_score"] == 82
    assert "probability" not in repr(payload).lower()


def test_level_inspector_omits_missing_optional_metrics():
    level = MarketLevel(
        id="GAMMA_FLIP-7590",
        level_type=LevelType.GAMMA_FLIP,
        price=7590.0,
        source=LevelSource.GEX_ENGINE,
        timestamp=datetime(2026, 9, 18, 9, 45),
        strength=50,
    )

    payload = build_level_inspector_payload(level=level, spot=7592.0)

    assert payload["metrics"] == {}
    assert "distance_percent" not in payload["summary"]
