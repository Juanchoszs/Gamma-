from datetime import datetime

from gex.application.market_intelligence.level_history import (
    LevelHistoryObservation,
    build_level_history_payload,
)
from gex.domain.market.intelligence import LevelSource, LevelType, MarketLevel
from gex.presentation.dashboard.level_history import build_level_history_figure


def _level(price: float, strength: int) -> MarketLevel:
    return MarketLevel(
        id=f"CALL_WALL-{price:g}", level_type=LevelType.CALL_WALL, price=price,
        source=LevelSource.GEX_ENGINE, timestamp=datetime(2026, 9, 18, 9, 30), strength=strength,
    )


def test_level_history_tracks_observed_ranked_levels_without_inference():
    payload = build_level_history_payload(
        symbol="SPX",
        observations=[
            LevelHistoryObservation(datetime(2026, 9, 18, 9, 30), 100.0, (_level(101.0, 80),)),
            LevelHistoryObservation(datetime(2026, 9, 18, 10, 0), 100.5, (_level(102.0, 85),)),
        ],
    )

    assert payload["observations"] == 2
    assert payload["series"][0]["points"][1]["price"] == 102.0
    assert "probability" not in repr(payload).lower()
    figure = build_level_history_figure(payload)
    assert figure.data
    assert len(figure.data[0].customdata[0]) == 5
    assert "Gamma" in figure.data[0].hovertemplate


def test_level_history_figure_filters_only_requested_level_types():
    payload = build_level_history_payload(
        symbol="SPX",
        observations=[
            LevelHistoryObservation(datetime(2026, 9, 18, 9, 30), 100.0, (
                _level(101.0, 80),
                MarketLevel(id="POC-100", level_type=LevelType.POC, price=100.0,
                            source=LevelSource.SESSION_PROFILE, timestamp=datetime(2026, 9, 18, 9, 30), strength=60),
            )),
        ],
    )

    figure = build_level_history_figure(payload, level_types=["POC"])

    assert [trace.name for trace in figure.data] == ["POC 1", "SPOT"]
