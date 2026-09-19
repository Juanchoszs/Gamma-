from __future__ import annotations

from datetime import datetime

from gex.application.market_intelligence import AlertConfig, AlertKind, AlertMonitor, evaluate_alerts
from gex.application.market_intelligence.service import build_market_intelligence_snapshot
from gex.domain.market.intelligence import LevelSource, LevelType, MarketLevel, SessionType


def _snapshot(*, spot: float, net_gex: float, strength: int, previous_spot: float | None = None):
    level = MarketLevel(
        id="CALL_WALL-100", level_type=LevelType.CALL_WALL, price=100.0,
        source=LevelSource.GEX_ENGINE, timestamp=datetime(2026, 9, 18, 10, 0),
        strength=strength, session=SessionType.REGULAR,
    )
    return build_market_intelligence_snapshot(
        symbol="SPX", spot=spot, timestamp=datetime(2026, 9, 18, 10, 0), levels=(level,),
        net_gex=net_gex, session=SessionType.REGULAR, data_status="LIVE", previous_spot=previous_spot,
    )


def test_alerts_emit_meaningful_regime_level_and_strength_transitions():
    previous = _snapshot(spot=99.0, net_gex=1_000_000.0, strength=60, previous_spot=98.0)
    current = _snapshot(spot=101.0, net_gex=-1_000_000.0, strength=80, previous_spot=99.0)

    alerts = evaluate_alerts(previous, current, config=AlertConfig(strength_change_threshold=10))

    kinds = {alert.kind for alert in alerts}
    assert AlertKind.GAMMA_REGIME_CHANGED in kinds
    assert AlertKind.LEVEL_STRENGTH_CHANGED in kinds
    assert AlertKind.LEVEL_RECLAIMED in kinds


def test_alert_monitor_is_quiet_on_first_observation_and_serializes_follow_up_events():
    monitor = AlertMonitor()
    previous = _snapshot(spot=99.0, net_gex=1_000_000.0, strength=60, previous_spot=98.0)
    current = _snapshot(spot=101.0, net_gex=-1_000_000.0, strength=80, previous_spot=99.0)

    assert monitor.observe(previous) == ()
    alerts = monitor.observe(current)

    assert alerts
    assert alerts[0].to_dict()["symbol"] == "SPX"


def test_alert_monitor_reset_forgets_the_previous_observation():
    monitor = AlertMonitor()
    previous = _snapshot(spot=99.0, net_gex=1_000_000.0, strength=60)
    current = _snapshot(spot=101.0, net_gex=-1_000_000.0, strength=80)

    monitor.observe(previous)
    monitor.reset("SPX")

    assert monitor.observe(current) == ()
