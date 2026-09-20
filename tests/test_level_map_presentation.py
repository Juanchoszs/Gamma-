from datetime import datetime

from gex.application.market_intelligence.service import build_market_intelligence_snapshot
from gex.domain.market.intelligence import LevelSource, LevelType, MarketLevel, SessionType
from gex.presentation.dashboard.level_map import build_level_map_figure
from gex.presentation.dashboard.terminal import filter_levels, levels_view


def _snapshot():
    level = MarketLevel(id="CALL_WALL-100", level_type=LevelType.CALL_WALL, price=100.0,
                        source=LevelSource.GEX_ENGINE, timestamp=datetime(2026, 9, 18, 10),
                        strength=80, session=SessionType.REGULAR)
    return build_market_intelligence_snapshot(symbol="SPX", spot=99.0, timestamp=level.timestamp,
                                              levels=(level,), net_gex=1_000_000.0,
                                              session=SessionType.REGULAR, data_status="LIVE")


def test_level_map_uses_normalized_levels_and_spot():
    figure = build_level_map_figure(_snapshot())

    assert len(figure.data) == 1
    assert figure.data[0].x[0] == 80
    assert figure.data[0].y[0] == 100.0
    assert figure.data[0].mode == "markers"
    assert figure.layout.xaxis.showspikes is True
    assert figure.layout.yaxis.showspikes is True


def test_levels_view_renders_interactive_unified_level_table():
    view = levels_view(_snapshot())

    assert "terminal-level-table-scroll" in view.className


def test_level_display_filters_preserve_only_requested_source():
    snapshot = _snapshot()

    visible = filter_levels(snapshot, sources=["SESSION_PROFILE"])

    assert visible == ()
