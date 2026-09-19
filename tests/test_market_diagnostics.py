from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from gex.application.market_intelligence import (
    DataFreshness,
    DataFreshnessConfig,
    build_symbol_diagnostics,
    classify_data_freshness,
    diagnostics_payload,
)


def test_classify_data_freshness_distinguishes_live_delayed_stale_and_disconnected():
    now = datetime(2026, 9, 18, 10, 0)
    config = DataFreshnessConfig(live_after_seconds=120, stale_after_seconds=900)

    assert classify_data_freshness(None, now=now, config=config) == (DataFreshness.DISCONNECTED, None)
    assert classify_data_freshness(now - timedelta(seconds=60), now=now, config=config)[0] is DataFreshness.LIVE
    assert classify_data_freshness(now - timedelta(seconds=300), now=now, config=config)[0] is DataFreshness.DELAYED
    assert classify_data_freshness(now - timedelta(seconds=1_200), now=now, config=config)[0] is DataFreshness.DATA_STALE


def test_build_symbol_diagnostics_produces_api_ready_counts_and_status():
    now = datetime(2026, 9, 18, 10, 0)
    diag = build_symbol_diagnostics(
        symbol="SPX",
        last_update=now - timedelta(seconds=30),
        options_count=1_200,
        expiration_count=4,
        strike_count=180,
        source="cboe",
        quality={"invalid_record_count": 2},
        calculation_ms=12.345,
        last_calculation=now,
        now=now,
    )

    payload = diag.to_dict()
    assert payload["symbol"] == "SPX"
    assert payload["available"] is True
    assert payload["data_status"] == "LIVE"
    assert payload["options_count"] == 1_200
    assert payload["expiration_count"] == 4
    assert payload["strike_count"] == 180
    assert payload["source"] == "cboe"
    assert payload["age_seconds"] == 30.0
    assert payload["quality"]["invalid_record_count"] == 2
    assert payload["calculation_ms"] == 12.345
    assert payload["last_calculation"] == now.isoformat()


def test_diagnostics_payload_collects_symbols_and_error_metadata():
    now = datetime(2026, 9, 18, 10, 0)
    diag = build_symbol_diagnostics(
        symbol="SPX",
        last_update=now - timedelta(seconds=30),
        options_count=100,
        now=now,
    )

    payload = diagnostics_payload(
        (diag,),
        api_status="OK",
        websocket_status="CONNECTE",
        last_error="SPX: transient",
        metadata={"market_open": True},
    )

    assert payload["api_status"] == "OK"
    assert payload["websocket_status"] == "CONNECTE"
    assert payload["last_error"] == "SPX: transient"
    assert payload["metadata"]["market_open"] is True
    assert payload["symbols"][0]["symbol"] == "SPX"


def test_data_freshness_config_rejects_invalid_thresholds():
    with pytest.raises(ValueError, match="live_after_seconds"):
        DataFreshnessConfig(live_after_seconds=-1)
    with pytest.raises(ValueError, match="stale_after_seconds"):
        DataFreshnessConfig(live_after_seconds=60, stale_after_seconds=30)
