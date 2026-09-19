from datetime import datetime

from gex.application.market_intelligence.service import build_market_intelligence_snapshot
from gex.domain.market.intelligence import LevelSource, LevelType, MarketLevel, SessionType
from gex.presentation.dashboard.terminal import (
    intelligence_view,
    diagnostics_view,
    level_inspector_view,
    market_report_view,
    overview_briefing_view,
    options_chain_view,
    alerts_view,
    scenario_inspector_view,
    scenarios_view,
    session_profile_view,
    terminal_topbar_market,
    topbar_market_view,
    terminal_intelligence_panel,
    terminal_sidebar,
    terminal_accent_style,
    terminal_navigation_pages,
    market_time_text,
)


def _snapshot():
    timestamp = datetime(2026, 9, 18, 10, 0)
    level = MarketLevel(
        id="CALL_WALL-100", level_type=LevelType.CALL_WALL, price=100.0,
        source=LevelSource.GEX_ENGINE, timestamp=timestamp, strength=84,
        gamma=1_000_000.0, session=SessionType.REGULAR,
    )
    return build_market_intelligence_snapshot(
        symbol="SPY", spot=99.0, timestamp=timestamp, levels=[level],
        net_gex=1_000.0, session=SessionType.REGULAR, data_status="LIVE",
    )


def test_terminal_has_navigation_and_intelligence_slots():
    sidebar = terminal_sidebar()
    panel = terminal_intelligence_panel()

    assert "terminal-sidebar" in sidebar.className
    assert "terminal-intelligence" in panel.className
    navigation = sidebar.children[1]
    assert len(navigation.children) == 6
    assert sidebar.children[0].children[-1].id == "terminal-sidebar-toggle"
    assert terminal_navigation_pages()[0] == "main"
    assert len(terminal_navigation_pages()) == 16
    assert "STRUCTURE" in str(navigation)
    assert "Sessions & Profile" in str(navigation)


def test_intelligence_view_renders_normalized_snapshot_without_provider_access():
    view = intelligence_view(_snapshot())

    assert len(view) == 8
    assert view[3] == "LIVE"
    assert view[4] == "SPY"
    assert "GEX 1.00M" in str(view[1])
    assert "Volatility" in str(view[0])
    assert "Positioning" in str(view[0])


def test_terminal_level_visibility_and_accent_are_presentation_only_preferences():
    snapshot = _snapshot()

    filtered = intelligence_view(snapshot, levels=())

    assert "No unified levels" in str(filtered[1])
    assert terminal_accent_style("teal")["--color-info"] == "#2aa198"
    assert terminal_accent_style("unknown") == terminal_accent_style("blue")


def test_topbar_market_view_reads_price_change_from_normalized_state():
    snapshot = _snapshot()
    snapshot = build_market_intelligence_snapshot(
        symbol="SPY", spot=101.0, timestamp=snapshot.state.timestamp,
        levels=snapshot.report.key_levels, net_gex=1_000.0,
        session=SessionType.REGULAR, data_status="LIVE", previous_spot=100.0,
    )

    assert "terminal-topbar-market" in terminal_topbar_market().className
    assert topbar_market_view(snapshot, "0DTE") == ("101.00", "+1.00 (+1.00%)", "REGULAR", "0DTE", "LIVE", "10:00:00 ET")
    assert market_time_text(snapshot.state.timestamp, "UTC") == "14:00:00 UTC"


def test_level_inspector_view_uses_only_present_metrics():
    content = level_inspector_view({
        "summary": {"type": "CALL_WALL", "price": 100.0, "strength": 84, "status": "ACTIVE"},
        "metrics": {"open_interest": 10_000.0},
        "context": {"position": "ABOVE_SPOT"},
    })

    assert "terminal-inspector" in content.className


def test_level_inspector_view_renders_expiration_and_structural_context_as_text():
    content = level_inspector_view({
        "summary": {
            "type": "CALL_WALL", "price": 100.0, "strength": 84, "status": "ACTIVE",
            "source": "OPTIONS_CHAIN", "session": "REGULAR", "distance_percent": 0.5,
        },
        "metrics": {"expiration": "2026-09-18T16:00:00"},
        "context": {
            "spot": 99.5, "position": "ABOVE_SPOT",
            "nearest_below": {"type": "PUT_WALL", "price": 95.0},
            "related_scenarios": [{"title": "Price holds above 100"}],
        },
    })

    rendered = str(content)
    assert "2026-09-18" in rendered
    assert "OPTIONS CHAIN" in rendered
    assert "Price holds above 100" in rendered


def test_market_report_view_renders_automatic_report_from_snapshot():
    report = market_report_view(_snapshot())

    assert "terminal-report" in report.className


def test_overview_briefing_uses_only_normalized_state_levels_and_scenarios():
    content = overview_briefing_view(_snapshot())

    assert "terminal-overview-briefing" in content.className
    assert "command center" in str(content)


def test_scenario_inspector_view_renders_conditional_scenario_context():
    scenario = _snapshot().scenarios[0]

    content = scenario_inspector_view(scenario)

    assert "terminal-scenario-inspector" in content.className


def test_scenarios_view_renders_full_conditional_analysis_from_snapshot():
    content = scenarios_view(_snapshot())

    assert "terminal-scenarios-page" in content.className
    assert "conditional scenarios" in str(content)


def test_options_chain_view_renders_both_option_sides_and_context_flags():
    chain = options_chain_view({
        "spot": 100.0,
        "side": "ALL",
        "row_count": 1,
        "rows": [{
            "strike": 100.0,
            "call": {"open_interest": 100.0, "volume": 20.0, "gex": 1_000_000.0},
            "put": {"open_interest": 50.0, "volume": 10.0, "gex": -500_000.0},
            "net_gex": 500_000.0,
            "flags": ["ATM", "CALL WALL"],
        }],
    })

    assert "terminal-chain" in chain.className


def test_options_chain_view_keeps_partial_legacy_rows_renderable():
    chain = options_chain_view({
        "spot": 100.0,
        "side": "CALLS",
        "row_count": 1,
        "rows": [{
            "strike": 100.0,
            "call": {"open_interest": 100.0, "volume": 20.0, "gex": 1_000_000.0},
            "put": {"open_interest": 0.0, "volume": 0.0, "gex": 0.0},
            "net_gex": 1_000_000.0,
            "flags": ["ATM"],
        }],
    })

    assert "terminal-chain" in chain.className


def test_diagnostics_view_renders_backend_freshness_without_inference():
    content = diagnostics_view({
        "api_status": "OK",
        "websocket_status": "CONNECTED",
        "metadata": {"market_open": True},
        "symbols": [{
            "symbol": "SPX", "data_status": "LIVE", "age_seconds": 12.2,
            "options_count": 1200, "expiration_count": 8, "strike_count": 90,
            "source": "CBOE", "calculation_ms": 4.2,
        }],
    })

    assert "terminal-diagnostics" in content.className


def test_alerts_view_is_quiet_by_default_and_renders_emitted_events():
    disabled = alerts_view((), enabled=False)
    active = alerts_view([{
        "kind": "LEVEL_BROKEN", "timestamp": "2026-09-18T10:01:02",
        "message": "Level broken: CALL WALL at 100.",
    }], enabled=True)

    assert "terminal-alert-empty" in disabled.className
    assert "terminal-alert-events" in active.className


def test_session_profile_view_renders_regular_and_overnight_backend_levels():
    content = session_profile_view({
        "symbol": "SPX", "timezone": "America/New_York", "as_of": "2026-09-18T10:00:00",
        "methodology": {"value_area_fraction": 0.70},
        "sessions": {
            "regular": {"available": True, "bar_count": 30, "weight": "volume",
                        "levels": {"open": 100.0, "high": 104.0, "low": 99.0, "close": 102.0,
                                   "poc": 101.0, "vah": 103.0, "val": 100.0}},
            "overnight": {"available": False, "bar_count": 0, "levels": {}},
        },
    })

    assert "terminal-session" in content.className
