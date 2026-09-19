from datetime import date, datetime

import pandas as pd

from gex.application.market_intelligence.options_chain import (
    OptionsChainConfig,
    available_expirations,
    build_options_chain_payload,
)
from gex.domain.market.intelligence import LevelSource, LevelType, MarketLevel


def _chain():
    return pd.DataFrame({
        "strike": [95.0, 100.0, 100.0, 105.0, 105.0],
        "type": ["P", "C", "P", "C", "P"],
        "expiry": [date(2026, 9, 18), date(2026, 9, 18), date(2026, 9, 18), date(2026, 9, 25), date(2026, 9, 25)],
        "open_interest": [10.0, 100.0, 80.0, 25.0, 15.0],
        "volume": [2.0, 40.0, 20.0, 5.0, 3.0],
        "gex": [-100.0, 500.0, -300.0, 200.0, -120.0],
        "iv": [0.2, 0.21, 0.22, 0.23, 0.24],
        "delta_bs": [-0.3, 0.5, -0.4, 0.25, -0.2],
    })


def test_options_chain_payload_uses_existing_metrics_and_marks_real_context():
    level = MarketLevel(
        id="CALL_WALL-100", level_type=LevelType.CALL_WALL, price=100.0,
        source=LevelSource.GEX_ENGINE, timestamp=datetime(2026, 9, 18), strength=90,
    )

    payload = build_options_chain_payload(chain=_chain(), spot=100.0, levels=[level])

    assert available_expirations(_chain()) == ["2026-09-18", "2026-09-25"]
    atm = next(row for row in payload["rows"] if row["strike"] == 100.0)
    assert atm["call"]["open_interest"] == 100.0
    assert atm["put"]["gex"] == -300.0
    assert {"ATM", "CALL WALL", "HIGH OI", "HIGH VOLUME"}.issubset(atm["flags"])
    assert "probability" not in repr(payload).lower()


def test_options_chain_payload_filters_by_expiry_and_side():
    payload = build_options_chain_payload(
        chain=_chain(),
        spot=100.0,
        config=OptionsChainConfig(expiration="2026-09-25", side="CALLS", strike_range_pct=10),
    )

    assert [row["strike"] for row in payload["rows"]] == [105.0]
    assert payload["rows"][0]["put"]["open_interest"] == 0.0


def test_options_chain_payload_filters_aggregated_strikes_by_metrics():
    payload = build_options_chain_payload(
        chain=_chain(), spot=100.0,
        config=OptionsChainConfig(
            strike_range_pct=10,
            min_volume=50,
            min_open_interest=150,
            min_abs_net_gex=100,
            min_abs_delta=0.4,
        ),
    )

    assert [row["strike"] for row in payload["rows"]] == [100.0]
    assert {"LARGE GEX", "HIGH IV"}.issubset(
        set(flag for row in build_options_chain_payload(chain=_chain(), spot=100.0)["rows"] for flag in row["flags"])
    )
