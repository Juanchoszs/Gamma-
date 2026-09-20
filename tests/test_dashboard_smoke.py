from pathlib import Path

import pandas as pd

from gex.presentation.dashboard import heatmap
from gex.presentation.dashboard.main import (
    available_overlay_days,
    create_app,
    exposure_fig,
    heatmap_fig,
    heatmap_bubbles_fig,
    heatmap_intraday_fig,
    _price_overlay,
    overlay_expiration_filter,
    overlay_flow_bubbles,
    overlay_layer_flags,
)
from gex.adapters.market_data.flowtape import expiration_of
from gex.application.options_flow.service import FlowBubble
from gex.domain.options.models import FlowSide, OptionType


def test_dashboard_uses_packaged_assets_and_registers_callbacks():
    app = create_app()
    assert Path(app.config.assets_folder).is_dir()
    assert any("heatmap-intraday.figure" in key for key in app.callback_map)
    assert any("options-flow-overlay.figure" in key for key in app.callback_map)
    assert any("workspace-title.children" in key for key in app.callback_map)
    assert any(
        any(item["id"] == "tab" for item in callback["inputs"])
        and "terminal-nav-link" in str(callback["output"])
        for callback in app.callback_map.values()
    )
    assert "terminal-settings-shortcut" in str(app.layout)
    assert "chart-command-bar" in str(app.layout)
    assert "chart-controls-menu" in str(app.layout)
    assert "overlay-flow-expiration-custom-wrap" in str(app.layout)
    assert any(
        "overlay-flow-expiration-custom-wrap.style" in key
        for key in app.callback_map
    )
    response = app.server.test_client().get("/healthz")
    assert response.status_code == 200
    assert response.get_json() == {"status": "ok", "service": "gex-dashboard"}


def test_chart_control_menu_keeps_overlay_filters_available_without_inline_radios():
    app = create_app()
    layout = str(app.layout)

    for control_id in (
        "overlay-flow-type",
        "overlay-flow-side",
        "overlay-flow-expiration",
        "overlay-min-premium",
        "overlay-min-volume",
        "overlay-layers",
    ):
        assert control_id in layout

    def find_by_id(component, target_id):
        if isinstance(component, (list, tuple)):
            for child in component:
                found = find_by_id(child, target_id)
                if found is not None:
                    return found
            return None
        if getattr(component, "id", None) == target_id:
            return component
        return find_by_id(getattr(component, "children", ()), target_id)

    assert find_by_id(app.layout, "overlay-flow-side").__class__.__name__ == "Dropdown"


def test_settings_expiration_updates_the_shared_expiration_bucket():
    app = create_app()

    callbacks = [
        callback for callback in app.callback_map.values()
        if any(item["id"] == "settings-expiry-bucket" for item in callback["inputs"])
    ]

    assert "settings-expiry-bucket" in str(app.layout)
    assert any(callback["output"].component_id == "bucket" for callback in callbacks)


def test_overlay_days_require_both_price_and_options_snapshot(monkeypatch):
    monkeypatch.setattr("gex.presentation.dashboard.main.store.price_days", lambda _: ["2026-08-19", "2026-08-20"])
    monkeypatch.setattr("gex.presentation.dashboard.main.store.snapshot_days", lambda _: ["2026-08-20"])
    assert available_overlay_days("SPX") == ["2026-08-20"]


def test_overlay_layer_flags_include_annotations_by_default():
    defaults = overlay_layer_flags(None)
    without_badges = overlay_layer_flags(["price", "spot", "call_wall"])

    assert defaults["show_annotations"] is True
    assert without_badges["show_annotations"] is False


def test_overlay_expiration_filter_resolves_custom_date():
    assert overlay_expiration_filter("ALL", "2026-09-25") == "ALL"
    assert overlay_expiration_filter("CUSTOM", "2026-09-25") == "CUSTOM:2026-09-25"
    assert overlay_expiration_filter("CUSTOM", "") == "CUSTOM"


def test_price_overlay_discards_zero_quotes_and_uses_last_close_when_needed(monkeypatch):
    invalid = pd.DataFrame({
        "timestamp": [pd.Timestamp("2026-09-20 15:59"), pd.Timestamp("2026-09-20 16:00")],
        "open": [0.0, 0.0], "high": [0.0, 0.0], "low": [0.0, 0.0], "close": [0.0, 0.0],
    })
    monkeypatch.setattr("gex.presentation.dashboard.main.store.load_prices", lambda *_: invalid)
    monkeypatch.setattr("gex.presentation.dashboard.main.store.load_history", lambda *_: pd.DataFrame())

    path = _price_overlay("ES", "2026-09-20", fallback_close=7725.25)

    assert path is not None
    assert path["close"].tolist() == [7725.25]
    assert (path[["open", "high", "low", "close"]] > 0).all().all()


def test_heatmap_price_axis_stays_near_spot_when_a_stale_zero_quote_exists(monkeypatch):
    chain = pd.DataFrame({
        "strike": [95.0, 100.0, 105.0], "type": ["P", "C", "C"],
        "gex": [-2_000_000.0, 4_000_000.0, 1_000_000.0], "gamma_bs": [0.01, 0.02, 0.015],
        "open_interest": [10, 20, 15], "volume": [2, 4, 1],
    })
    zero_path = pd.DataFrame({
        "timestamp": [pd.Timestamp("2026-09-20 16:00")],
        "open": [0.0], "high": [0.0], "low": [0.0], "close": [0.0],
    })
    monkeypatch.setattr("gex.presentation.dashboard.main._chain_for_day", lambda *_: (chain, 100.0))
    monkeypatch.setattr("gex.presentation.dashboard.main._price_overlay", lambda *_args, **_kwargs: zero_path)
    monkeypatch.setattr("gex.presentation.dashboard.main.metrics.key_levels", lambda *_args, **_kwargs: {})
    monkeypatch.setattr("gex.presentation.dashboard.main.metrics.zero_gamma", lambda *_args, **_kwargs: None)

    figure = heatmap_fig("SPX", "en", "2026-09-20", window=0.05)

    assert figure.layout.yaxis.range == (95.0, 105.0)


def test_exposure_graph_preserves_both_manual_axis_ranges():
    frame = pd.DataFrame({
        "strike": [95.0, 100.0, 105.0],
        "gex": [1.0, -2.0, 3.0],
        "open_interest": [10, 20, 30],
        "type": ["P", "C", "C"],
    })

    figure = exposure_fig(
        frame, 100.0, None, "gex", "GEX", "en",
        relayout={
            "xaxis.range[0]": -5.0,
            "xaxis.range[1]": 5.0,
            "yaxis.range": [98.0, 102.0],
        },
    )

    assert figure.layout.xaxis.range == (-5.0, 5.0)
    assert figure.layout.yaxis.range == (98.0, 102.0)
    assert figure.layout.xaxis.autorange is False
    assert figure.layout.yaxis.autorange is False


def test_intraday_heatmap_uses_real_spots_and_never_synthesizes_candles(monkeypatch):
    frame = pd.DataFrame({
        "strike": [95.0, 100.0, 105.0],
        "spot": [100.0, 100.0, 100.0],
        "gex": [-2_000_000.0, 4_000_000.0, -1_000_000.0],
        "open_interest": [10, 20, 15],
        "volume": [2, 4, 1],
        "type": ["P", "C", "P"],
    })
    monkeypatch.setattr(
        heatmap,
        "_snapshots",
        lambda *_: ([(pd.Timestamp("2026-09-06 09:30"), frame),
                     (pd.Timestamp("2026-09-06 09:31"), frame)], 100.0),
    )
    monkeypatch.setattr(heatmap.metrics, "key_levels", lambda *_args, **_kwargs: {"call_wall": 105.0, "put_support": 95.0})
    monkeypatch.setattr(heatmap.metrics, "zero_gamma", lambda *_args, **_kwargs: 100.0)

    figure = heatmap.build_intraday_heatmap("SPX", "es", "2026-09-06", 0.05)

    assert figure.data[0].type == "heatmap"
    assert figure.data[1].type == "scatter"
    assert all(trace.type != "candlestick" for trace in figure.data)
    assert len(figure.layout.shapes) == 3


def test_intraday_heatmap_returns_an_empty_state_when_no_snapshot_exists(monkeypatch):
    monkeypatch.setattr(heatmap, "_snapshots", lambda *_: ([], 0.0))
    figure = heatmap.build_intraday_heatmap("SPX", "es", "2026-09-06", 0.05)
    assert figure.layout.annotations


def test_intraday_heatmap_preserves_both_manual_ranges(monkeypatch):
    frame = pd.DataFrame({
        "strike": [95.0, 100.0, 105.0],
        "spot": [100.0, 100.0, 100.0],
        "gex": [-2_000_000.0, 4_000_000.0, -1_000_000.0],
        "open_interest": [10, 20, 15],
        "volume": [2, 4, 1],
        "type": ["P", "C", "P"],
    })
    monkeypatch.setattr(
        heatmap,
        "_snapshots",
        lambda *_: ([(pd.Timestamp("2026-09-06 09:30"), frame),
                     (pd.Timestamp("2026-09-06 09:31"), frame)], 100.0),
    )
    monkeypatch.setattr(heatmap.metrics, "key_levels", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(heatmap.metrics, "zero_gamma", lambda *_args, **_kwargs: 100.0)

    figure = heatmap.build_intraday_heatmap(
        "SPX", "es", "2026-09-06", 0.05,
        relayout={
            "xaxis.range": ["2026-09-06 09:30", "2026-09-06 09:31"],
            "yaxis.range": [98.0, 102.0],
        },
    )

    assert figure.layout.xaxis.range == ("2026-09-06 09:30", "2026-09-06 09:31")
    assert figure.layout.yaxis.range == (98.0, 102.0)


def test_bubbles_filter_by_size_and_cap_rendered_points(monkeypatch):
    frame = pd.DataFrame({
        "strike": [95.0, 100.0, 105.0, 110.0],
        "spot": [100.0] * 4,
        "volume": [1, 10, 100, 1000],
        "open_interest": [1, 10, 100, 1000],
        "type": ["P", "C", "P", "C"],
        "expiry": ["2026-09-11"] * 4,
        "iv": [0.2] * 4,
        "t_years": [0.01] * 4,
        "gex": [1.0, 2.0, 3.0, 4.0],
    })
    next_frame = frame.copy()
    next_frame["volume"] = [2, 20, 200, 2000]
    monkeypatch.setattr(
        "gex.presentation.dashboard.main._load_snaps_for_heat",
        lambda *_: (
            [
                (pd.Timestamp("2026-09-06 09:30"), frame),
                (pd.Timestamp("2026-09-06 09:31"), next_frame),
            ],
            100.0,
        ),
    )

    figure = heatmap_bubbles_fig(
        "SPX", "es", "2026-09-06", 0.10, min_size=100, max_points=2,
    )

    bubble_traces = [trace for trace in figure.data if trace.name.startswith(("Calls", "Puts"))]
    assert sum(len(trace.x) for trace in bubble_traces) == 2
    assert all("1 contratos" not in hover for trace in bubble_traces for hover in trace.hovertext)


def test_intraday_heatmap_uses_recorded_spot_and_does_not_expand_a_single_snapshot(monkeypatch):
    frame = pd.DataFrame({
        "strike": [95.0, 100.0, 105.0],
        "spot": [100.0, 100.0, 100.0],
        "volume": [10.0, 20.0, 30.0],
        "open_interest": [50.0, 60.0, 70.0],
        "type": ["P", "C", "C"],
        "expiry": ["2026-09-11"] * 3,
        "iv": [0.2] * 3,
        "t_years": [0.01] * 3,
        "gex": [-1_000_000.0, 2_000_000.0, 1_000_000.0],
    })
    monkeypatch.setattr(
        "gex.presentation.dashboard.main._load_snaps_for_heat",
        lambda *_: ([(pd.Timestamp("2026-09-06 09:30"), frame)], 100.0),
    )
    monkeypatch.setattr(
        "gex.presentation.dashboard.main.store.load_prices",
        lambda *_: pd.DataFrame({
            "timestamp": [pd.Timestamp("2026-09-06 09:30")],
            "open": [0.0], "high": [0.0], "low": [0.0], "close": [0.0],
        }),
    )

    figure = heatmap_intraday_fig("SPX", "en", "2026-09-06", 0.05)

    heatmap_trace = next(trace for trace in figure.data if trace.type == "heatmap")
    assert list(heatmap_trace.x) == ["09:30"]
    assert figure.layout.yaxis.range == (95.0, 105.0)
    assert all(0.0 not in trace.y for trace in figure.data if trace.type == "scatter" and trace.y is not None)


def test_overlay_flow_bubbles_cache_reuses_unchanged_tape(monkeypatch):
    prints = [
        {
            "t": pd.Timestamp("2026-09-18 10:00").timestamp(),
            "strike": 650.0,
            "type": "C",
            "price": 1.25,
            "size": 10.0,
            "side": "BUY",
            "notional": 1_250.0,
        }
    ]
    calls = {"build": 0}

    monkeypatch.setattr(
        "gex.presentation.dashboard.main.TAPE.recent_prints",
        lambda *_args, **_kwargs: prints,
    )

    def fake_build(events, **_kwargs):
        calls["build"] += 1
        return [
            FlowBubble(
                timestamp=pd.Timestamp("2026-09-18 10:00").to_pydatetime(),
                strike=650.0,
                option_type=OptionType.CALL,
                size=12.0,
                premium=1_250.0,
                volume=10.0,
                event_count=1,
                average_price=1.25,
                side=FlowSide.BUY,
            )
        ]

    monkeypatch.setattr("gex.presentation.dashboard.main.build_flow_bubbles", fake_build)
    monkeypatch.setattr("gex.presentation.dashboard.main._OVERLAY_FLOW_BUBBLE_CACHE", {})

    first = overlay_flow_bubbles("SPY", 650.0, 0, 0, "ALL", "ALL", "ALL", 0.03)
    second = overlay_flow_bubbles("SPY", 650.0, 0, 0, "ALL", "ALL", "ALL", 0.03)
    prints.append({**prints[0], "t": 1_800_000_001.0, "notional": 2_500.0})
    third = overlay_flow_bubbles("SPY", 650.0, 0, 0, "ALL", "ALL", "ALL", 0.03)

    assert len(first) == len(second) == len(third) == 1
    assert calls["build"] == 2


def test_flowtape_parses_expiration_when_streamer_symbol_encodes_date():
    assert expiration_of(".SPXW260918C6500") == "2026-09-18"
    assert expiration_of(".SPXW260919P6400") == "2026-09-19"
    assert expiration_of(".SPX7710C") is None


def test_overlay_flow_expiration_filter_uses_tape_expiration(monkeypatch):
    prints = [
        {
            "t": pd.Timestamp("2026-09-18 10:00").timestamp(),
            "strike": 650.0,
            "expiration": "2026-09-18",
            "type": "C",
            "price": 1.25,
            "size": 10.0,
            "side": "BUY",
            "notional": 1_250.0,
        },
        {
            "t": pd.Timestamp("2026-09-18 10:01").timestamp(),
            "strike": 651.0,
            "expiration": "2026-09-19",
            "type": "C",
            "price": 1.25,
            "size": 10.0,
            "side": "BUY",
            "notional": 1_250.0,
        },
    ]
    monkeypatch.setattr(
        "gex.presentation.dashboard.main.TAPE.recent_prints",
        lambda *_args, **_kwargs: prints,
    )
    monkeypatch.setattr("gex.presentation.dashboard.main._OVERLAY_FLOW_BUBBLE_CACHE", {})

    zero_dte = overlay_flow_bubbles("SPY", 650.0, 0, 0, "CALLS", "BUY", "0DTE", 0.03)

    assert len(zero_dte) == 1
    assert zero_dte[0].strike == 650.0
    assert zero_dte[0].expiration is not None


def test_overlay_flow_min_volume_filter_uses_tape_size(monkeypatch):
    prints = [
        {
            "t": pd.Timestamp("2026-09-18 10:00").timestamp(),
            "strike": 650.0,
            "expiration": "2026-09-18",
            "type": "C",
            "price": 1.25,
            "size": 4.0,
            "side": "BUY",
            "notional": 500.0,
        },
        {
            "t": pd.Timestamp("2026-09-18 10:01").timestamp(),
            "strike": 651.0,
            "expiration": "2026-09-18",
            "type": "C",
            "price": 1.25,
            "size": 25.0,
            "side": "BUY",
            "notional": 3_125.0,
        },
    ]
    monkeypatch.setattr(
        "gex.presentation.dashboard.main.TAPE.recent_prints",
        lambda *_args, **_kwargs: prints,
    )
    monkeypatch.setattr("gex.presentation.dashboard.main._OVERLAY_FLOW_BUBBLE_CACHE", {})

    bubbles = overlay_flow_bubbles("SPY", 650.0, 0, 10, "CALLS", "BUY", "0DTE", 0.03)

    assert len(bubbles) == 1
    assert bubbles[0].strike == 651.0
    assert bubbles[0].volume == 25.0
