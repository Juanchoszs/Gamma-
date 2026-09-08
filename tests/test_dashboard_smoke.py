from pathlib import Path

import pandas as pd

from gex.presentation.dashboard import heatmap
from gex.presentation.dashboard.main import (
    available_overlay_days,
    create_app,
    exposure_fig,
    heatmap_bubbles_fig,
)


def test_dashboard_uses_packaged_assets_and_registers_callbacks():
    app = create_app()
    assert Path(app.config.assets_folder).is_dir()
    assert any("heatmap-intraday.figure" in key for key in app.callback_map)
    assert any("options-flow-overlay.figure" in key for key in app.callback_map)


def test_overlay_days_require_both_price_and_options_snapshot(monkeypatch):
    monkeypatch.setattr("gex.presentation.dashboard.main.store.price_days", lambda _: ["2026-08-19", "2026-08-20"])
    monkeypatch.setattr("gex.presentation.dashboard.main.store.snapshot_days", lambda _: ["2026-08-20"])
    assert available_overlay_days("SPX") == ["2026-08-20"]


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
    monkeypatch.setattr(
        "gex.presentation.dashboard.main._load_snaps_for_heat",
        lambda *_: (
            [
                (pd.Timestamp("2026-09-06 09:30"), frame),
                (pd.Timestamp("2026-09-06 09:31"), frame),
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
