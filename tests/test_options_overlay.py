from __future__ import annotations

import pandas as pd

from gex.application.options_flow.dto import GEXLevel
from gex.application.options_flow.service import FlowBubble
from gex.application.options_flow.dto import OptionsOverlayViewModel
from gex.domain.options.models import FlowAggressiveness, FlowSide, OptionType
from gex.presentation.dashboard import options_overlay


def _chain() -> pd.DataFrame:
    return pd.DataFrame({
        "strike": [95.0, 100.0, 105.0, 105.0, 95.0],
        "type": ["P", "C", "C", "P", "P"],
        "gex": [-1_000_000.0, 3_000_000.0, 9_000_000.0, -2_000_000.0, -8_000_000.0],
        "open_interest": [100, 200, 400, 50, 500],
        "volume": [10, 20, 40, 5, 50],
    })


def test_overlay_uses_real_candles_and_hoverable_gex_levels(monkeypatch):
    bars = pd.DataFrame({
        "timestamp": pd.to_datetime(["2026-09-06 09:30", "2026-09-06 09:31"]),
        "open": [100.0, 101.0], "high": [102.0, 103.0],
        "low": [99.0, 100.0], "close": [101.0, 102.0],
    })

    fig = options_overlay.build_options_overlay(
        "SPY", _chain(), 101.0, 100.0,
        {"call_wall": 105.0, "put_support": 95.0}, "2026-09-06", 0.05,
        price_series=bars,
    )

    assert fig.data[0].type == "candlestick"
    names = {trace.name for trace in fig.data}
    assert {"Call Wall", "Put Wall", "Gamma Flip", "Current price"} <= names
    call_wall = next(trace for trace in fig.data if trace.name == "Call Wall")
    assert "Open interest" in call_wall.hovertemplate
    assert call_wall.customdata[0][1] == 400


def test_overlay_preserves_manual_zoom_and_renders_snapshot_activity(monkeypatch):
    bars = pd.DataFrame({
        "timestamp": pd.to_datetime(["2026-09-06 09:30", "2026-09-06 09:31"]),
        "open": [100.0, 101.0], "high": [102.0, 103.0],
        "low": [99.0, 100.0], "close": [101.0, 102.0],
    })
    snapshots = [(pd.Timestamp("2026-09-06 09:30"), _chain()),
                 (pd.Timestamp("2026-09-06 09:31"), _chain())]

    fig = options_overlay.build_options_overlay(
        "SPY", _chain(), 101.0, 100.0,
        {"call_wall": 105.0, "put_support": 95.0}, "2026-09-06", 0.05,
        snapshots=snapshots,
        relayout={"yaxis.range[0]": 98.0, "yaxis.range[1]": 106.0},
        price_series=bars,
    )

    assert fig.layout.yaxis.range == (98.0, 106.0)
    assert "Active call GEX" in {trace.name for trace in fig.data}


def test_overlay_merges_partial_axis_events_with_current_ranges():
    merged = options_overlay.merge_relayout_ranges(
        {"yaxis.range[0]": 98.0, "yaxis.range[1]": 106.0},
        {"layout": {
            "xaxis": {"range": ["2026-09-06 09:30", "2026-09-06 10:30"]},
            "yaxis": {"range": [98.0, 106.0]},
        }},
    )

    assert merged["xaxis.range"] == ["2026-09-06 09:30", "2026-09-06 10:30"]
    assert merged["yaxis.range[0]"] == 98.0
    assert merged["yaxis.range[1]"] == 106.0


def test_overlay_keeps_both_axes_scrollable(monkeypatch):
    bars = pd.DataFrame({
        "timestamp": pd.date_range("2026-09-07 09:30", periods=2, freq="min"),
        "open": [100.0, 101.0], "high": [101.0, 102.0],
        "low": [99.0, 100.0], "close": [100.5, 101.5],
    })
    fig = options_overlay.build_options_overlay(
        "SPY", _chain(), 101.0, None, {}, "2026-09-07", 0.05,
        price_series=bars,
    )
    assert fig.layout.yaxis.fixedrange is False
    assert fig.layout.xaxis.fixedrange is False


def test_overlay_does_not_create_synthetic_candles():
    fig = options_overlay.build_options_overlay(
        "SPY", _chain(), 100.0, None, {}, "2026-09-06", 0.05,
    )

    assert not fig.data
    assert fig.layout.annotations


def test_overlay_renders_three_call_and_put_levels(monkeypatch):
    bars = pd.DataFrame({
        "timestamp": pd.to_datetime(["2026-09-06 09:30", "2026-09-06 09:31"]),
        "open": [100.0, 101.0], "high": [102.0, 103.0],
        "low": [99.0, 100.0], "close": [101.0, 102.0],
    })
    chain = pd.DataFrame({
        "strike": [102.0, 103.0, 104.0, 98.0, 97.0, 96.0],
        "type": ["C", "C", "C", "P", "P", "P"],
        "gex": [6.0, 5.0, 4.0, -6.0, -5.0, -4.0],
        "open_interest": [1, 2, 3, 4, 5, 6],
        "volume": [1, 2, 3, 4, 5, 6],
    })

    fig = options_overlay.build_options_overlay(
        "SPY", chain, 101.0, None,
        {
            "call_walls": [102.0, 103.0, 104.0],
            "put_supports": [98.0, 97.0, 96.0],
        },
        "2026-09-06", 0.05,
        price_series=bars,
    )

    names = {trace.name for trace in fig.data}
    assert {"Call Wall", "Call Wall 2", "Call Wall 3",
            "Put Wall", "Put Wall 2", "Put Wall 3"} <= names


def test_overlay_includes_previous_session_and_keeps_walls_in_view(monkeypatch):
    current = pd.DataFrame({
        "timestamp": pd.to_datetime(["2026-09-07 09:30", "2026-09-07 09:31"]),
        "open": [100.0, 101.0], "high": [102.0, 103.0],
        "low": [99.0, 100.0], "close": [101.0, 102.0],
    })
    previous = current.copy()
    previous["timestamp"] = previous["timestamp"] - pd.Timedelta(days=1)

    fig = options_overlay.build_options_overlay(
        "SPY", _chain(), 101.0, None,
        {"call_walls": [105.0, 106.0, 107.0],
         "put_supports": [95.0, 94.0, 93.0]},
        "2026-09-07", 0.05, timeframe="2d",
        price_series=current,
        previous_price_series=previous,
    )

    assert len(fig.data[0].x) == 4
    assert fig.layout.yaxis.range[0] < 93.0
    assert fig.layout.yaxis.range[1] > 107.0
    wall = next(trace for trace in fig.data if trace.name == "Call Wall")
    assert wall.line.width <= 2.5


def test_overlay_timeframe_changes_candle_count(monkeypatch):
    bars = pd.DataFrame({
        "timestamp": pd.date_range("2026-09-07 09:30", periods=12, freq="min"),
        "open": range(100, 112), "high": range(101, 113),
        "low": range(99, 111), "close": range(100, 112),
    })

    one_minute = options_overlay.build_options_overlay(
        "SPY", _chain(), 101.0, None, {}, "2026-09-07", 0.05, timeframe="1m",
        price_series=bars,
    )
    five_minutes = options_overlay.build_options_overlay(
        "SPY", _chain(), 101.0, None, {}, "2026-09-07", 0.05, timeframe="5m",
        price_series=bars,
    )

    assert len(one_minute.data[0].x) == 12
    assert len(five_minutes.data[0].x) == 3


def test_overlay_supports_15m_and_30m_timeframes(monkeypatch):
    bars = pd.DataFrame({
        "timestamp": pd.date_range("2026-09-07 09:30", periods=60, freq="min"),
        "open": range(100, 160),
        "high": range(101, 161),
        "low": range(99, 159),
        "close": range(100, 160),
    })

    fifteen = options_overlay.build_options_overlay(
        "SPY", _chain(), 130.0, None, {}, "2026-09-07", 0.05, timeframe="15m",
        price_series=bars,
    )
    thirty = options_overlay.build_options_overlay(
        "SPY", _chain(), 130.0, None, {}, "2026-09-07", 0.05, timeframe="30m",
        price_series=bars,
    )

    assert len(fifteen.data[0].x) == 4
    assert len(thirty.data[0].x) == 2


def test_overlay_aggregates_hourly_bars_from_real_prices(monkeypatch):
    bars = pd.DataFrame({
        "timestamp": pd.date_range("2026-09-07 09:30", periods=120, freq="min"),
        "open": range(100, 220),
        "high": range(101, 221),
        "low": range(99, 219),
        "close": range(100, 220),
    })

    figure = options_overlay.build_options_overlay(
        "SPY", _chain(), 150.0, None, {}, "2026-09-07", 0.05, timeframe="1h",
        price_series=bars,
    )

    assert figure.data[0].type == "candlestick"
    assert len(figure.data[0].x) == 2
    assert figure.data[0].open[0] == 159
    assert figure.data[0].high[0] == 190
    assert figure.data[0].low[0] == 158
    assert figure.data[0].close[0] == 189


def test_overlay_uses_white_spot_line_when_ohlc_is_degenerate(monkeypatch):
    bars = pd.DataFrame({
        "timestamp": pd.date_range("2026-09-07 09:30", periods=3, freq="min"),
        "open": [100.0, 100.0, 100.0],
        "high": [100.0, 100.0, 100.0],
        "low": [100.0, 100.0, 100.0],
        "close": [100.0, 100.0, 100.0],
    })

    figure = options_overlay.build_options_overlay(
        "SPY", _chain(), 100.0, None, {}, "2026-09-07", 0.05, timeframe="1m",
        price_series=bars,
    )

    assert figure.data[0].type == "scatter"
    assert figure.data[0].name == "Spot"
    assert figure.data[0].line.color == options_overlay.COLORS["spot"]
    assert all(trace.type != "candlestick" for trace in figure.data)


def test_overlay_preserves_selected_pan_or_zoom_mode(monkeypatch):
    bars = pd.DataFrame({
        "timestamp": pd.date_range("2026-09-07 09:30", periods=3, freq="min"),
        "open": [100.0, 101.0, 102.0], "high": [101.0, 102.0, 103.0],
        "low": [99.0, 100.0, 101.0], "close": [100.5, 101.5, 102.5],
    })

    fig = options_overlay.build_options_overlay(
        "SPY", _chain(), 101.0, None, {}, "2026-09-07", 0.05,
        relayout={"dragmode": "zoom"},
        price_series=bars,
    )

    assert fig.layout.dragmode == "zoom"


def test_overlay_short_timeframes_do_not_prepend_dead_session(monkeypatch):
    live = pd.DataFrame({
        "timestamp": pd.date_range("2026-09-07 09:30", periods=2, freq="min"),
        "open": [100.0, 101.0], "high": [101.0, 102.0],
        "low": [99.0, 100.0], "close": [100.5, 101.5],
    })
    previous = live.copy()
    previous["timestamp"] -= pd.Timedelta(days=1)

    fig = options_overlay.build_options_overlay(
        "SPY", _chain(), 101.0, None, {}, "2026-09-07", 0.05, timeframe="1m",
        price_series=live,
        previous_price_series=previous,
    )

    assert len(fig.data[0].x) == 2
    assert not fig.layout.xaxis.rangebreaks


def test_overlay_renders_flow_bubbles_without_missing_tooltip_fields(monkeypatch):
    bars = pd.DataFrame({
        "timestamp": pd.date_range("2026-09-07 09:30", periods=3, freq="min"),
        "open": [100.0, 101.0, 102.0], "high": [101.0, 102.0, 103.0],
        "low": [99.0, 100.0, 101.0], "close": [100.5, 101.5, 102.5],
    })
    bubbles = [
        FlowBubble(
            timestamp=pd.Timestamp("2026-09-07 09:31").to_pydatetime(),
            strike=102.0,
            option_type=OptionType.CALL,
            size=18.0,
            premium=125_000.0,
            volume=50,
            event_count=2,
            average_price=None,
            side=FlowSide.UNKNOWN,
            aggressiveness=FlowAggressiveness.AGGRESSIVE,
        )
    ]

    fig = options_overlay.build_options_overlay(
        "SPY", _chain(), 101.0, None, {}, "2026-09-07", 0.05,
        flow_bubbles=bubbles,
        price_series=bars,
    )

    trace = next(item for item in fig.data if item.name == "CALL Flow")
    assert trace.y[0] == 102.0
    assert trace.marker.size[0] == 18.0
    assert "Aggressiveness: AGGRESSIVE" in trace.text[0]
    assert "Avg price" not in trace.text[0]
    assert "None" not in trace.text[0]


def test_overlay_omits_unknown_flow_aggressiveness_from_tooltip():
    bubble = FlowBubble(
        timestamp=pd.Timestamp("2026-09-07 09:31").to_pydatetime(),
        strike=102.0,
        option_type=OptionType.CALL,
        size=18.0,
        premium=125_000.0,
        volume=50,
        event_count=2,
        average_price=None,
        side=FlowSide.UNKNOWN,
    )

    hover = options_overlay._flow_hover_text(bubble)

    assert "Aggressiveness" not in hover


def test_overlay_can_render_from_prepared_view_model_without_loading_prices(monkeypatch):
    bars = pd.DataFrame({
        "timestamp": pd.date_range("2026-09-07 09:30", periods=3, freq="min"),
        "open": [100.0, 101.0, 102.0], "high": [101.0, 102.0, 103.0],
        "low": [99.0, 100.0, 101.0], "close": [100.5, 101.5, 102.5],
    })

    fig = options_overlay.build_options_overlay_from_view_model(
        OptionsOverlayViewModel(
            symbol="SPY",
            price_series=bars,
            current_price=101.0,
            chain=_chain(),
            gamma_flip=100.0,
            keys={"call_wall": 105.0, "put_support": 95.0},
            day="2026-09-07",
            window=0.05,
        )
    )

    assert fig.data[0].type == "candlestick"
    assert {"Call Wall", "Put Wall", "Gamma Flip", "Current price"} <= {trace.name for trace in fig.data}


def test_overlay_renders_prepared_gex_levels_without_chain_resolution(monkeypatch):
    bars = pd.DataFrame({
        "timestamp": pd.date_range("2026-09-07 09:30", periods=3, freq="min"),
        "open": [100.0, 101.0, 102.0], "high": [101.0, 102.0, 103.0],
        "low": [99.0, 100.0, 101.0], "close": [100.5, 101.5, 102.5],
    })
    levels = [
        GEXLevel("Call Wall", 105.0, 9_000_000.0, open_interest=400, volume=40,
                 color_key="call_wall", glow_key="call_wall_glow"),
        GEXLevel("Put Wall", 95.0, -8_000_000.0, open_interest=500, volume=50,
                 color_key="put_wall", glow_key="put_wall_glow"),
        GEXLevel("Gamma Flip", 100.0, 0.0, style="dash",
                 color_key="flip", glow_key="flip_glow"),
    ]
    monkeypatch.setattr(
        options_overlay,
        "_overlay_levels",
        lambda *_: (_ for _ in ()).throw(AssertionError("renderer should use prepared levels")),
    )

    fig = options_overlay.build_options_overlay_from_view_model(
        OptionsOverlayViewModel(
            symbol="SPY",
            price_series=bars,
            current_price=101.0,
            chain=None,
            gamma_flip=None,
            keys={},
            day="2026-09-07",
            window=0.05,
            gex_levels=levels,
        )
    )

    names = {trace.name for trace in fig.data}
    assert {"Call Wall", "Put Wall", "Gamma Flip"} <= names
    call_wall = next(trace for trace in fig.data if trace.name == "Call Wall")
    assert call_wall.customdata[0][1] == 400


def test_overlay_layer_flags_can_hide_price_levels_spot_and_flow(monkeypatch):
    bars = pd.DataFrame({
        "timestamp": pd.date_range("2026-09-07 09:30", periods=3, freq="min"),
        "open": [100.0, 101.0, 102.0], "high": [101.0, 102.0, 103.0],
        "low": [99.0, 100.0, 101.0], "close": [100.5, 101.5, 102.5],
    })
    bubbles = [
        FlowBubble(
            timestamp=pd.Timestamp("2026-09-07 09:31").to_pydatetime(),
            strike=102.0,
            option_type=OptionType.CALL,
            size=18.0,
            premium=125_000.0,
            volume=50,
            event_count=2,
            average_price=None,
            side=FlowSide.BUY,
        )
    ]
    view_model = OptionsOverlayViewModel(
        symbol="SPY",
        price_series=bars,
        current_price=101.0,
        chain=_chain(),
        gamma_flip=100.0,
        keys={"call_wall": 105.0, "put_support": 95.0},
        day="2026-09-07",
        window=0.05,
        flow_bubbles=bubbles,
    )

    fig = options_overlay.build_options_overlay_from_view_model(
        view_model,
        show_price=False,
        show_call_wall=False,
        show_put_wall=False,
        show_gamma_flip=False,
        show_current_price=False,
        show_flow=False,
    )

    names = {trace.name for trace in fig.data}
    assert "Price" not in names
    assert "Spot" not in names
    assert "Current price" not in names
    assert "Call Wall" not in names
    assert "Put Wall" not in names
    assert "Gamma Flip" not in names
    assert "CALL Flow" not in names


def test_overlay_annotations_layer_hides_badges_without_hiding_traces():
    bars = pd.DataFrame({
        "timestamp": pd.date_range("2026-09-07 09:30", periods=3, freq="min"),
        "open": [100.0, 101.0, 102.0], "high": [101.0, 102.0, 103.0],
        "low": [99.0, 100.0, 101.0], "close": [100.5, 101.5, 102.5],
    })
    view_model = OptionsOverlayViewModel(
        symbol="SPY",
        price_series=bars,
        current_price=101.0,
        chain=_chain(),
        gamma_flip=100.0,
        keys={"call_wall": 105.0, "put_support": 95.0},
        day="2026-09-07",
        window=0.05,
    )

    with_badges = options_overlay.build_options_overlay_from_view_model(view_model)
    without_badges = options_overlay.build_options_overlay_from_view_model(
        view_model,
        show_annotations=False,
    )

    assert len(with_badges.layout.annotations) > 0
    assert len(without_badges.layout.annotations) == 0
    assert {"Call Wall", "Put Wall", "Gamma Flip", "Current price"} <= {
        trace.name for trace in without_badges.data
    }
