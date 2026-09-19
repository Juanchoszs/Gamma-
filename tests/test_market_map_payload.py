from __future__ import annotations

from datetime import date, datetime

import pandas as pd
import pytest

from gex.application.market_intelligence import MarketMapConfig, build_market_map_payload
from gex.domain.market.intelligence import (
    LevelSource,
    LevelStatus,
    LevelType,
    MarketLevel,
    SessionType,
)
from gex.domain.market.state import build_market_state
from gex.presentation.dashboard.market_map import build_market_map_figure


def _chain() -> pd.DataFrame:
    expiry = date(2026, 9, 18)
    return pd.DataFrame({
        "strike": [7580.0, 7580.0, 7590.0, 7600.0, 7600.0, 7610.0],
        "type": ["P", "C", "C", "C", "P", "C"],
        "expiry": [expiry] * 6,
        "gex": [-2_000_000.0, 100_000.0, 5_000_000.0, 1_000_000.0, -500_000.0, 3_000_000.0],
        "open_interest": [42_100.0, 1_000.0, 35_000.0, 38_000.0, 2_000.0, 19_100.0],
        "volume": [12_400.0, 100.0, 8_200.0, 15_420.0, 300.0, 4_200.0],
    })


def _level(level_type: LevelType, price: float, strength: int) -> MarketLevel:
    return MarketLevel(
        id=f"SPX-{level_type.value}-{price:g}",
        level_type=level_type,
        price=price,
        source=LevelSource.GEX_ENGINE,
        timestamp=datetime(2026, 9, 18, 9, 45),
        strength=strength,
        session=SessionType.REGULAR,
        status=LevelStatus.ACTIVE,
    )


def test_market_map_payload_combines_exposure_rows_levels_and_state():
    levels = (
        _level(LevelType.PUT_WALL, 7580.0, 82),
        _level(LevelType.GEX_WALL, 7590.0, 88),
        _level(LevelType.CALL_WALL, 7600.0, 87),
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

    payload = build_market_map_payload(
        symbol="SPX",
        timestamp=datetime(2026, 9, 18, 9, 45),
        spot=7592.45,
        chain=_chain(),
        levels=levels,
        state=state,
    )

    assert payload["symbol"] == "SPX"
    assert payload["spot"] == 7592.45
    assert payload["exposure_axis"] == "strike"
    assert payload["positioning_axis"] == "net_gex"
    assert payload["state"]["gamma_regime"] == "POSITIVE_GAMMA"
    assert payload["levels"][0]["type"] == "PUT_WALL"
    strikes = [row["strike"] for row in payload["rows"]]
    assert strikes == sorted(strikes)
    row_7600 = next(row for row in payload["rows"] if row["strike"] == 7600.0)
    assert row_7600["call_gex"] == 1_000_000.0
    assert row_7600["put_gex"] == -500_000.0
    assert row_7600["net_gex"] == 500_000.0
    assert row_7600["expiration_count"] == 1

    figure = build_market_map_figure(payload)
    assert figure.layout.xaxis.showspikes is True
    assert figure.layout.yaxis.showspikes is True


def test_market_map_payload_filters_strike_window_and_limits_rows():
    payload = build_market_map_payload(
        symbol="SPX",
        timestamp=datetime(2026, 9, 18, 9, 45),
        spot=7592.45,
        chain=_chain(),
        levels=(),
        config=MarketMapConfig(strike_window_pct=0.1, max_rows=2),
    )

    assert len(payload["rows"]) <= 2
    assert all(abs(row["distance_percent"]) <= 0.1 for row in payload["rows"])


def test_market_map_payload_rejects_invalid_inputs():
    with pytest.raises(ValueError, match="spot"):
        build_market_map_payload(
            symbol="SPX",
            timestamp=datetime(2026, 9, 18),
            spot=0,
            chain=_chain(),
            levels=(),
        )
    with pytest.raises(ValueError, match="max_rows"):
        MarketMapConfig(max_rows=0)
    with pytest.raises(ValueError, match="strike_window_pct"):
        MarketMapConfig(strike_window_pct=-1)
