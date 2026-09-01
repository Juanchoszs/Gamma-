from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from gex import backfill
from gex.domain import (
    DataQuality,
    MarketDataState,
    MarketStateContext,
    evaluate_data_quality,
    get_quality_config,
    resolve_market_state,
)
from gex.metrics import ET


def test_quality_config_selects_provider_thresholds():
    assert get_quality_config("cboe").valid_seconds == 30
    assert get_quality_config("dxfeed_live").valid_seconds == 5
    assert get_quality_config("native_futures").valid_seconds == 10

    assert evaluate_data_quality(6, "dxfeed") == DataQuality.WARNING
    assert evaluate_data_quality(6, "cboe") == DataQuality.VALID


@pytest.mark.parametrize(
    ("quality", "expected"),
    [
        (DataQuality.VALID, MarketDataState.LIVE),
        (DataQuality.WARNING, MarketDataState.DELAYED),
        (DataQuality.STALE, MarketDataState.DELAYED),
        (DataQuality.EXPIRED, MarketDataState.DELAYED),
        (DataQuality.INVALID, MarketDataState.NO_DATA),
    ],
)
def test_market_state_keeps_stale_in_data_quality(quality, expected):
    context = MarketStateContext(
        is_market_open=True,
        current_time_et=datetime.now(ET),
        provider="cboe",
        data_age_seconds=100,
        data_quality=quality,
        snapshot_timestamp=None,
    )
    assert resolve_market_state(context) == expected


def test_backfill_uses_live_dex_sign_convention(monkeypatch):
    day = date(2026, 7, 27)
    chain = pd.DataFrame(
        [
            {
                "instrument_id": "C",
                "expiry": day + timedelta(days=30),
                "type": "C",
                "strike": 100.0,
                "close": 5.0,
                "open_interest": 10.0,
                "volume": 1.0,
            },
            {
                "instrument_id": "P",
                "expiry": day + timedelta(days=30),
                "type": "P",
                "strike": 100.0,
                "close": 5.0,
                "open_interest": 10.0,
                "volume": 1.0,
            },
        ]
    )
    monkeypatch.setattr(backfill, "spot_from_parity", lambda *_: 100.0)
    monkeypatch.setattr(
        backfill.greeks,
        "implied_vol",
        lambda price, s, k, t, r, is_call: np.full(len(chain), 0.2),
    )
    monkeypatch.setattr(
        backfill.greeks,
        "gamma",
        lambda s, k, t, r, sigma: np.ones(len(chain)),
    )
    monkeypatch.setattr(
        backfill.greeks,
        "call_delta",
        lambda s, k, t, r, sigma: np.full(len(chain), 0.5),
    )
    monkeypatch.setattr(backfill.metrics, "zero_gamma", lambda *_: None)

    result = backfill.build_day(chain, "SPX", day, persist_chain=False)

    assert result is not None
    assert result["net_dex"] == pytest.approx(0.0)
    assert result["_deltas"]["delta_bs"].tolist() == [0.5, -0.5]
