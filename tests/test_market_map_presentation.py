from gex.presentation.dashboard.market_map import build_market_map_figure


def test_market_map_figure_uses_backend_exposure_rows_and_levels():
    figure = build_market_map_figure({
        "symbol": "SPX", "spot": 100.0,
        "rows": [{
            "strike": 100.0, "call_gex": 1_000_000.0, "put_gex": -500_000.0,
            "call_open_interest": 100.0, "put_open_interest": 50.0,
            "call_volume": 20.0, "put_volume": 10.0, "distance_percent": 0.0,
        }],
        "levels": [{"type": "CALL_WALL", "price": 101.0, "strength": 80}],
    })

    assert len(figure.data) == 2
    assert figure.data[0].name == "Call GEX"
    assert figure.data[1].name == "Put GEX"


def test_market_map_figure_has_honest_empty_state():
    figure = build_market_map_figure({"rows": []})

    assert figure.layout.annotations[0].text == "No market-map rows are available."


def test_market_map_labels_only_decision_anchors():
    figure = build_market_map_figure({
        "symbol": "SPX", "spot": 100.0,
        "rows": [{
            "strike": 100.0, "call_gex": 1_000_000.0, "put_gex": -500_000.0,
            "call_open_interest": 100.0, "put_open_interest": 50.0,
            "call_volume": 20.0, "put_volume": 10.0, "distance_percent": 0.0,
        }],
        "levels": [
            {"type": "CALL_WALL", "price": 101.0, "strength": 70},
            {"type": "CALL_WALL", "price": 102.0, "strength": 80},
            {"type": "PUT_WALL", "price": 99.0, "strength": 90},
            {"type": "GAMMA_FLIP", "price": 100.5, "strength": 0},
            {"type": "GEX_WALL", "price": 98.0, "strength": 95},
        ],
    })

    labels = [annotation.text for annotation in figure.layout.annotations]
    assert labels == ["SPOT", "CALL WALL", "PUT WALL", "GAMMA FLIP"]
