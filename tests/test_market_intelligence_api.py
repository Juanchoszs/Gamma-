from __future__ import annotations

from datetime import date, datetime

import pandas as pd
from flask import Flask

from gex.domain.gex import metrics
from gex.domain.gex.metrics import SummaryMetrics
from gex.infrastructure.scheduling.scheduler import STATE
from gex.presentation.api.api import _clear_market_intelligence_cache, register_api
from gex.application.market_intelligence import MarketIntelligenceConfig
from gex.presentation.api.api import _market_intelligence


def _chain() -> pd.DataFrame:
    expiry = date(2026, 9, 18)
    return pd.DataFrame({
        "strike": [7580.0, 7590.0, 7600.0, 7610.0],
        "type": ["P", "C", "C", "C"],
        "expiry": [expiry, expiry, expiry, expiry],
        "gex": [-2_000_000.0, 5_000_000.0, 1_000_000.0, 3_000_000.0],
        "dex": [-1.0, 1.0, 1.0, 1.0],
        "open_interest": [42_100.0, 35_000.0, 38_000.0, 19_100.0],
        "volume": [12_400.0, 8_200.0, 15_420.0, 4_200.0],
        "spot": [7592.45, 7592.45, 7592.45, 7592.45],
        "iv": [0.20, 0.20, 0.20, 0.20],
        "t_years": [0.01, 0.01, 0.01, 0.01],
    })


def _summary() -> SummaryMetrics:
    return SummaryMetrics(
        timestamp=datetime(2026, 9, 18, 9, 45),
        symbol="SPX",
        spot=7592.45,
        net_gex=12_500_000.0,
        zero_gamma=7590.0,
        pc_oi=1.1,
        pc_volume=0.9,
        net_gex_0dte=12_500_000.0,
        net_dex=1_000_000.0,
    )


def _client(monkeypatch):
    _clear_market_intelligence_cache()
    app = Flask(__name__)
    register_api(app)
    monkeypatch.setattr("gex.presentation.api.api.market_is_open", lambda: True)
    monkeypatch.setattr("gex.domain.gex.metrics.rates.current_rate", lambda: 0.04)
    monkeypatch.setattr("gex.adapters.persistence.store.previous_close_spot", lambda _symbol, *_args, **_kwargs: 7592.45)
    monkeypatch.setattr("gex.adapters.persistence.store.price_days", lambda _symbol: [])
    monkeypatch.setattr("gex.adapters.persistence.store.load_prices", lambda _symbol, day: pd.DataFrame())
    with STATE.lock:
        STATE.per_symbol.clear()
        st = STATE.get("SPX")
        st.summary = _summary()
        st.enriched = _chain()
    return app.test_client()


def test_react_terminal_canonicalizes_duplicate_public_base(monkeypatch):
    client = _client(monkeypatch)

    overview = client.get("/terminal/terminal?bucket=0DTE")
    base = client.get("/terminal?bucket=0DTE")
    module = client.get("/terminal/terminal/map?symbol=SPY")

    assert overview.status_code == 308
    assert overview.headers["Location"] == "/terminal/?bucket=0DTE"
    assert base.status_code == 308
    assert base.headers["Location"].endswith("/terminal/?bucket=0DTE")
    assert module.status_code == 308
    assert module.headers["Location"] == "/terminal/map?symbol=SPY"


def test_market_state_endpoint_returns_structured_state(monkeypatch):
    client = _client(monkeypatch)

    response = client.get("/api/v1/SPX/market/state?bucket=Tout")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["symbol"] == "SPX"
    assert payload["spot"] == 7592.45
    assert payload["gamma_regime"] == "POSITIVE_GAMMA"
    assert payload["data_status"] == "DATA_STALE"
    assert payload["previous_spot"] == 7592.45
    assert payload["price_change"] == 0.0
    assert payload["price_change_percent"] == 0.0
    assert payload["major_gamma_level"]["type"] in {"GEX_WALL", "GAMMA_FLIP"}


def test_market_intelligence_accepts_configured_gamma_threshold(monkeypatch):
    _client(monkeypatch)

    snapshot = _market_intelligence("SPX", "Tout", config=MarketIntelligenceConfig(neutral_gex_threshold=20_000_000))

    assert snapshot is not None
    assert snapshot.state.gamma_regime.value == "NEUTRAL_GAMMA"


def test_market_intelligence_reuses_same_snapshot_within_short_refresh_window(monkeypatch):
    _client(monkeypatch)
    calls = 0
    original = metrics.compute_levels

    def counted(*args, **kwargs):
        nonlocal calls
        calls += 1
        return original(*args, **kwargs)

    monkeypatch.setattr("gex.presentation.api.api.metrics.compute_levels", counted)

    first = _market_intelligence("SPX", "Tout")
    second = _market_intelligence("SPX", "Tout")

    assert first is second
    assert calls == 1


def test_market_scenarios_endpoint_returns_conditional_scenarios(monkeypatch):
    client = _client(monkeypatch)

    response = client.get("/api/v1/SPX/market/scenarios?bucket=Tout")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["symbol"] == "SPX"
    assert payload["scenarios"]
    assert payload["scenarios"][0]["trigger"]
    assert payload["scenarios"][0]["invalidation"]
    assert "probability" not in repr(payload).lower()


def test_market_report_endpoint_returns_automatic_report(monkeypatch):
    client = _client(monkeypatch)

    response = client.get("/api/v1/SPX/market/report?bucket=Tout")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["symbol"] == "SPX"
    assert payload["key_levels"]
    assert payload["positioning_summary"]
    assert payload["structure_summary"]
    assert payload["scenarios"]


def test_market_report_endpoint_localizes_analysis_to_spanish(monkeypatch):
    client = _client(monkeypatch)

    response = client.get("/api/v1/SPX/market/report?bucket=Tout&lang=es")

    assert response.status_code == 200
    payload = response.get_json()
    rendered = repr(payload)
    assert "Concentracion" in rendered or "El regimen" in rendered
    assert "Call concentration" not in rendered


def test_price_history_endpoint_resamples_stored_sessions_without_inventing_bars(monkeypatch):
    client = _client(monkeypatch)
    frame = pd.DataFrame({
        "timestamp": ["2026-09-17 09:30:00", "2026-09-17 09:31:00", "2026-09-18 09:30:00"],
        "open": [100.0, 101.0, 102.0], "high": [101.0, 102.0, 103.0],
        "low": [99.0, 100.0, 101.0], "close": [100.5, 101.5, 102.5],
        "volume": [10.0, 20.0, 30.0],
    })
    monkeypatch.setattr("gex.adapters.persistence.store.price_days", lambda _symbol: ["2026-09-17", "2026-09-18"])
    monkeypatch.setattr("gex.adapters.persistence.store.load_prices", lambda _symbol, _day: frame)

    response = client.get("/api/v1/SPX/market/prices/history?days=2&interval=5m")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["sessions"] == ["2026-09-17", "2026-09-18"]
    assert payload["requested_sessions"] == 2
    assert payload["available_sessions"] == 2
    assert payload["interval"] == "5m"
    assert len(payload["rows"]) == 2
    assert payload["rows"][0]["timestamp"] == "2026-09-17T09:30:00-04:00"
    assert payload["rows"][0]["open"] == 100.0
    assert payload["rows"][0]["high"] == 102.0
    assert payload["rows"][0]["volume"] == 60.0


def test_market_report_endpoint_includes_session_profile_levels(monkeypatch):
    client = _client(monkeypatch)
    previous = pd.DataFrame({
        "timestamp": ["2026-09-17 16:05:00", "2026-09-17 20:00:00"],
        "open": [7588.0, 7590.0],
        "high": [7590.0, 7592.0],
        "low": [7587.0, 7589.0],
        "close": [7589.0, 7591.0],
        "volume": [100.0, 300.0],
    })
    current = pd.DataFrame({
        "timestamp": ["2026-09-18 09:00:00", "2026-09-18 09:30:00", "2026-09-18 09:31:00"],
        "open": [7591.0, 7592.0, 7594.0],
        "high": [7594.0, 7595.0, 7596.0],
        "low": [7590.0, 7591.0, 7592.0],
        "close": [7593.0, 7594.0, 7595.0],
        "volume": [200.0, 500.0, 1_000.0],
    })
    monkeypatch.setattr("gex.adapters.persistence.store.price_days", lambda _symbol: ["2026-09-17", "2026-09-18"])
    monkeypatch.setattr(
        "gex.adapters.persistence.store.load_prices",
        lambda _symbol, day: previous if day == "2026-09-17" else current,
    )

    response = client.get("/api/v1/SPX/market/report?bucket=Tout")

    assert response.status_code == 200
    payload = response.get_json()
    level_types = {level["type"] for level in payload["key_levels"]}
    assert {"POC", "VAH", "VAL", "OVH", "OVL"} & level_types
    session_level = next(level for level in payload["key_levels"] if level["source"] == "SESSION_PROFILE")
    assert session_level["metadata"]["bar_count"] > 0


def test_market_map_endpoint_returns_positioning_rows_levels_and_state(monkeypatch):
    client = _client(monkeypatch)

    response = client.get("/api/v1/SPX/market/map?bucket=Tout")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["symbol"] == "SPX"
    assert payload["spot"] == 7592.45
    assert payload["rows"]
    assert payload["levels"]
    assert payload["state"]["symbol"] == "SPX"
    assert {"strike", "call_gex", "put_gex", "net_gex"}.issubset(payload["rows"][0])
    assert "probability" not in repr(payload).lower()


def test_market_overlay_endpoint_returns_normalized_price_and_gex_contract(monkeypatch):
    client = _client(monkeypatch)

    response = client.get("/api/v1/SPX/market/overlay?bucket=Tout&flow_type=CALLS&min_premium=1000")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["symbol"] == "SPX"
    assert payload["current_price"] == 7592.45
    assert {"price_series", "gex_levels", "flow_bubbles", "market_regime", "filters", "source"}.issubset(payload)
    assert payload["filters"]["flow_type"] == "CALLS"
    assert all("price" in level and "name" in level for level in payload["gex_levels"])


def test_react_chart_suite_serializes_existing_dash_figures(monkeypatch):
    client = _client(monkeypatch)

    response = client.get("/api/v1/SPX/market/charts?names=market-map-chart,unified-level-map&bucket=Tout")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["symbol"] == "SPX"
    assert set(payload["charts"]) == {"market-map-chart", "unified-level-map"}
    assert all(chart and chart["data"] for chart in payload["charts"].values())


def test_react_chart_suite_rejects_unknown_figures(monkeypatch):
    client = _client(monkeypatch)

    response = client.get("/api/v1/SPX/market/charts?names=not-a-real-chart")

    assert response.status_code == 400
    assert "not allowed" in response.get_json()["error"]


def test_react_chart_suite_accepts_the_primary_dash_overlay_contract(monkeypatch):
    client = _client(monkeypatch)

    response = client.get(
        "/api/v1/SPX/market/charts?names=options-flow-overlay&series=calls,net"
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert "options-flow-overlay" in payload["charts"]


def test_options_chain_endpoint_returns_highlighted_strike_rows(monkeypatch):
    client = _client(monkeypatch)

    response = client.get("/api/v1/SPX/options/chain?range_pct=5&side=ALL")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["spot"] == 7592.45
    assert payload["available_expirations"] == ["2026-09-18"]
    assert payload["rows"]
    assert {"strike", "call", "put", "net_gex", "flags"}.issubset(payload["rows"][0])
    assert any("ATM" in row["flags"] for row in payload["rows"])


def test_options_chain_endpoint_excludes_structurally_invalid_contracts(monkeypatch):
    client = _client(monkeypatch)
    invalid = pd.DataFrame({
        "strike": [-1.0], "type": ["C"], "expiry": [date(2026, 9, 18)],
        "gex": [9_999_999_999.0], "open_interest": [1_000_000.0], "volume": [1_000_000.0],
    })
    with STATE.lock:
        STATE.get("SPX").enriched = pd.concat([_chain(), invalid], ignore_index=True)
    _clear_market_intelligence_cache()

    response = client.get("/api/v1/SPX/options/chain?range_pct=5&side=ALL")

    assert response.status_code == 200
    assert all(row["strike"] > 0 for row in response.get_json()["rows"])


def test_expiry_map_endpoint_returns_a_real_strike_by_expiry_matrix(monkeypatch):
    client = _client(monkeypatch)

    response = client.get("/api/v1/SPX/market/expiry-map?metric=gex&expiries=3&strikes=5")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["symbol"] == "SPX"
    assert payload["as_of"] == "2026-09-18T09:45:00"
    assert payload["source"] == "cboe"
    assert payload["metric"] == "gex"
    assert payload["expirations"] == ["2026-09-18"]
    assert payload["rows"]
    assert payload["nearest_strike"] == 7590.0
    assert len(payload["rows"][0]["values"]) == len(payload["expirations"])

    invalid = client.get("/api/v1/SPX/market/expiry-map?metric=iv")
    assert invalid.status_code == 400


def test_level_history_endpoint_returns_only_saved_snapshot_observations(monkeypatch):
    client = _client(monkeypatch)
    snapshots = [
        (datetime(2026, 9, 18, 9, 30), _chain()),
        (datetime(2026, 9, 18, 10, 0), _chain().assign(spot=7600.0)),
    ]
    monkeypatch.setattr("gex.adapters.persistence.store.snapshot_days", lambda _symbol: ["2026-09-18"])
    monkeypatch.setattr("gex.adapters.persistence.store.load_day_snapshots", lambda *_args, **_kwargs: snapshots)

    response = client.get("/api/v1/SPX/market/levels/history?date=2026-09-18&bucket=Tout")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["day"] == "2026-09-18"
    assert payload["observations"] == 2
    assert len(payload["spot"]) == 2
    assert payload["series"]
    assert payload["sampling"]["strategy"] == "evenly_spaced_saved_snapshots"


def test_market_level_inspector_endpoint_returns_selected_level_context(monkeypatch):
    client = _client(monkeypatch)
    report = client.get("/api/v1/SPX/market/report?bucket=Tout").get_json()
    level_id = report["key_levels"][0]["id"]

    response = client.get(f"/api/v1/SPX/market/levels/{level_id}?bucket=Tout")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["level"]["id"] == level_id
    assert payload["summary"]["id"] == level_id
    assert payload["summary"]["source"]
    assert "strength_score" in payload["methodology"]
    assert "spot" in payload["context"]
    assert "probability" not in repr(payload).lower()


def test_market_level_inspector_endpoint_404s_for_unknown_level(monkeypatch):
    client = _client(monkeypatch)

    response = client.get("/api/v1/SPX/market/levels/UNKNOWN-1?bucket=Tout")

    assert response.status_code == 404
    assert response.get_json()["error"] == "niveau introuvable"


def test_market_session_endpoint_returns_regular_and_overnight_profiles(monkeypatch):
    client = _client(monkeypatch)
    previous = pd.DataFrame({
        "timestamp": ["2026-09-17 16:05:00", "2026-09-17 20:00:00"],
        "open": [7588.0, 7590.0],
        "high": [7590.0, 7592.0],
        "low": [7587.0, 7589.0],
        "close": [7589.0, 7591.0],
        "volume": [100.0, 300.0],
    })
    current = pd.DataFrame({
        "timestamp": ["2026-09-18 09:00:00", "2026-09-18 09:30:00", "2026-09-18 09:31:00"],
        "open": [7591.0, 7592.0, 7594.0],
        "high": [7594.0, 7595.0, 7596.0],
        "low": [7590.0, 7591.0, 7592.0],
        "close": [7593.0, 7594.0, 7595.0],
        "volume": [200.0, 500.0, 1_000.0],
    })
    monkeypatch.setattr("gex.adapters.persistence.store.price_days", lambda _symbol: ["2026-09-17", "2026-09-18"])
    monkeypatch.setattr(
        "gex.adapters.persistence.store.load_prices",
        lambda _symbol, day: previous if day == "2026-09-17" else current,
    )

    response = client.get("/api/v1/SPX/market/session?date=2026-09-18")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["symbol"] == "SPX"
    assert payload["sessions"]["regular"]["available"] is True
    assert payload["sessions"]["regular"]["levels"]["high"] == 7596.0
    assert payload["sessions"]["overnight"]["available"] is True
    assert payload["sessions"]["overnight"]["levels"]["low"] == 7587.0


def test_market_session_endpoint_evaluates_historical_day_at_its_session_close(monkeypatch):
    client = _client(monkeypatch)
    previous = pd.DataFrame({
        "timestamp": ["2026-09-16 16:05:00", "2026-09-16 20:00:00"],
        "open": [7500.0, 7501.0], "high": [7502.0, 7504.0],
        "low": [7498.0, 7500.0], "close": [7501.0, 7503.0],
        "volume": [100.0, 200.0],
    })
    historical = pd.DataFrame({
        "timestamp": ["2026-09-17 09:00:00", "2026-09-17 09:30:00", "2026-09-17 15:59:00"],
        "open": [7503.0, 7504.0, 7507.0], "high": [7505.0, 7508.0, 7512.0],
        "low": [7502.0, 7503.0, 7506.0], "close": [7504.0, 7507.0, 7510.0],
        "volume": [150.0, 250.0, 350.0],
    })
    monkeypatch.setattr(
        "gex.adapters.persistence.store.price_days",
        lambda _symbol: ["2026-09-16", "2026-09-17", "2026-09-18"],
    )
    monkeypatch.setattr(
        "gex.adapters.persistence.store.load_prices",
        lambda _symbol, day: previous if day == "2026-09-16" else historical,
    )

    response = client.get("/api/v1/SPX/market/session?date=2026-09-17")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["as_of"].startswith("2026-09-17T16:00:00")
    assert payload["sessions"]["regular"]["available"] is True
    assert payload["sessions"]["regular"]["levels"]["high"] == 7512.0
    assert payload["sessions"]["overnight"]["levels"]["low"] == 7498.0


def test_market_session_endpoint_reports_unavailable_profiles_without_bars(monkeypatch):
    client = _client(monkeypatch)
    monkeypatch.setattr("gex.adapters.persistence.store.price_days", lambda _symbol: [])
    monkeypatch.setattr("gex.adapters.persistence.store.load_prices", lambda _symbol, day: pd.DataFrame())

    response = client.get("/api/v1/SPX/market/session?date=2026-09-18")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["sessions"]["regular"]["available"] is False
    assert payload["sessions"]["overnight"]["available"] is False


def test_market_session_endpoint_rejects_an_invalid_date(monkeypatch):
    client = _client(monkeypatch)

    response = client.get("/api/v1/SPX/market/session?date=not-a-date")

    assert response.status_code == 400
    assert response.get_json()["error"] == "fecha inválida; usa YYYY-MM-DD"


def test_market_intelligence_endpoints_return_404_before_first_pull(monkeypatch):
    client = _client(monkeypatch)
    with STATE.lock:
        STATE.per_symbol.clear()

    response = client.get("/api/v1/SPX/market/report")

    assert response.status_code == 404
    assert "error" in response.get_json()


def test_diagnostics_endpoint_reports_freshness_counts_and_connection_state(monkeypatch):
    client = _client(monkeypatch)
    monkeypatch.setattr("gex.adapters.market_data.rtquote.credentials_present", lambda: False)
    monkeypatch.setattr("gex.adapters.external.tt_web.connection_status", lambda: ("absent", "Sin credenciales"))

    response = client.get("/api/v1/diagnostics")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["api_status"] == "OK"
    assert payload["websocket_status"] == "ABSENT"
    assert payload["metadata"]["market_open"] is True
    assert payload["metadata"]["symbol_count"] == 1
    symbol = payload["symbols"][0]
    assert symbol["symbol"] == "SPX"
    assert symbol["available"] is True
    assert symbol["data_status"] in {"LIVE", "DELAYED", "DATA_STALE"}
    assert symbol["options_count"] == 4
    assert symbol["expiration_count"] == 1
    assert symbol["strike_count"] == 4
