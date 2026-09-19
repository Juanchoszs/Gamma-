from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd

from gex.application.options_flow.levels import build_gex_levels
from gex.application.options_flow.service import (
    OptionsFlowOverlayConfig,
    build_flow_bubbles,
    events_from_records,
    premium_for,
)
from gex.domain.options.models import FlowAggressiveness, FlowSide, OptionType


def test_premium_uses_multiplier_and_never_negative():
    assert premium_for(1.25, 10, 100) == 1250.0
    assert premium_for(-1.25, 10, 100) == 0.0


def test_events_use_record_multiplier_metadata_when_available():
    events = events_from_records([
        {
            "timestamp": "2026-09-18 10:00",
            "strike": 650,
            "type": "C",
            "price": 1.25,
            "quantity": 10,
            "contract_multiplier": 50,
        },
        {
            "timestamp": "2026-09-18 10:01",
            "strike": 651,
            "type": "C",
            "price": 1.25,
            "quantity": 10,
        },
    ], symbol="SPX", contract_multiplier=100)

    assert [event.premium for event in events] == [625.0, 1250.0]


def test_events_parse_aggressiveness_without_inventing_it():
    events = events_from_records([
        {
            "timestamp": "2026-09-18 10:00",
            "strike": 650,
            "type": "C",
            "price": 1.25,
            "quantity": 10,
            "aggressiveness": "AGGRESSIVE",
        },
        {
            "timestamp": "2026-09-18 10:01",
            "strike": 651,
            "type": "P",
            "price": 1.25,
            "quantity": 10,
            "aggression": "passive",
        },
        {
            "timestamp": "2026-09-18 10:02",
            "strike": 652,
            "type": "P",
            "price": 1.25,
            "quantity": 10,
            "aggressiveness": "at ask maybe",
        },
    ], symbol="SPX", contract_multiplier=100)

    assert [event.aggressiveness for event in events] == [
        FlowAggressiveness.AGGRESSIVE,
        FlowAggressiveness.PASSIVE,
        FlowAggressiveness.UNKNOWN,
    ]


def test_flow_aggregation_preserves_aggressive_activity():
    events = events_from_records([
        {
            "timestamp": "2026-09-18 10:00:05",
            "strike": 650,
            "type": "C",
            "price": 1.0,
            "quantity": 10,
            "side": "BUY",
            "aggressiveness": "AGGRESSIVE",
        },
        {
            "timestamp": "2026-09-18 10:00:20",
            "strike": 650,
            "type": "C",
            "price": 2.0,
            "quantity": 10,
            "side": "BUY",
            "aggressiveness": "PASSIVE",
        },
    ], symbol="SPX", contract_multiplier=100)

    bubbles = build_flow_bubbles(events, config=OptionsFlowOverlayConfig(aggregation_seconds=60))

    assert len(bubbles) == 2
    assert {bubble.aggressiveness for bubble in bubbles} == {
        FlowAggressiveness.AGGRESSIVE,
        FlowAggressiveness.PASSIVE,
    }
    aggressive = next(bubble for bubble in bubbles if bubble.aggressiveness is FlowAggressiveness.AGGRESSIVE)
    assert aggressive.tooltip["aggressiveness"] == "AGGRESSIVE"


def test_flow_aggregation_and_log_bubble_sizing():
    now = datetime(2026, 9, 18, 10, 0, 5)
    events = events_from_records([
        {
            "timestamp": now,
            "strike": 650,
            "type": "C",
            "price": 1.0,
            "quantity": 100,
            "side": "BUY",
        },
        {
            "timestamp": now + timedelta(seconds=20),
            "strike": 650,
            "type": "C",
            "price": 2.0,
            "quantity": 100,
            "side": "BUY",
        },
        {
            "timestamp": now,
            "strike": 645,
            "type": "P",
            "price": 10.0,
            "quantity": 1000,
            "side": "SELL",
        },
    ], symbol="SPY", contract_multiplier=100)

    bubbles = build_flow_bubbles(events, current_price=650)

    assert len(bubbles) == 2
    call = next(bubble for bubble in bubbles if bubble.option_type is OptionType.CALL)
    put = next(bubble for bubble in bubbles if bubble.option_type is OptionType.PUT)
    assert call.event_count == 2
    assert call.premium == 30_000.0
    assert put.size > call.size
    assert call.size >= OptionsFlowOverlayConfig().min_bubble_size


def test_flow_filters_by_type_premium_and_visible_strike_range():
    events = events_from_records([
        {"timestamp": "2026-09-18 10:00", "strike": 650, "type": "C", "price": 1, "quantity": 50},
        {"timestamp": "2026-09-18 10:00", "strike": 651, "type": "P", "price": 100, "quantity": 50},
        {"timestamp": "2026-09-18 10:00", "strike": 800, "type": "P", "price": 100, "quantity": 50},
    ], symbol="SPY", contract_multiplier=100)
    config = OptionsFlowOverlayConfig(
        min_premium=100_000,
        option_types=frozenset({OptionType.PUT}),
        visible_strike_range=0.02,
    )

    bubbles = build_flow_bubbles(events, current_price=650, config=config)

    assert len(bubbles) == 1
    assert bubbles[0].strike == 651
    assert bubbles[0].option_type is OptionType.PUT


def test_flow_filters_by_side_and_rejects_negative_oi_or_volume():
    events = events_from_records([
        {"timestamp": "2026-09-18 10:00", "strike": 650, "type": "C", "price": 10, "quantity": 10, "side": "BUY"},
        {"timestamp": "2026-09-18 10:00", "strike": 651, "type": "C", "price": 10, "quantity": 10, "side": "SELL"},
        {"timestamp": "2026-09-18 10:00", "strike": 652, "type": "P", "price": 10, "quantity": 10, "volume": -1},
        {"timestamp": "2026-09-18 10:00", "strike": 653, "type": "P", "price": 10, "quantity": 10, "open_interest": -5},
    ], symbol="SPY", contract_multiplier=100)
    config = OptionsFlowOverlayConfig(sides=frozenset({FlowSide.BUY}))

    bubbles = build_flow_bubbles(events, current_price=650, config=config)

    assert len(events) == 2
    assert len(bubbles) == 1
    assert bubbles[0].side is FlowSide.BUY


def test_flow_filters_by_expiration_bucket_and_keeps_expiration_for_tooltip():
    events = events_from_records([
        {
            "timestamp": "2026-09-18 10:00",
            "expiration": "2026-09-18",
            "strike": 650,
            "type": "C",
            "price": 10,
            "quantity": 10,
        },
        {
            "timestamp": "2026-09-18 10:00",
            "expiration": "2026-09-19",
            "strike": 651,
            "type": "C",
            "price": 10,
            "quantity": 10,
        },
        {
            "timestamp": "2026-09-18 10:00",
            "expiration": "2026-09-25",
            "strike": 652,
            "type": "C",
            "price": 10,
            "quantity": 10,
        },
        {
            "timestamp": "2026-09-18 10:00",
            "expiration": "2026-10-16",
            "strike": 653,
            "type": "C",
            "price": 10,
            "quantity": 10,
        },
    ], symbol="SPY", contract_multiplier=100)

    zero_dte = build_flow_bubbles(events, config=OptionsFlowOverlayConfig(expiration_filter="0DTE"))
    one_dte = build_flow_bubbles(events, config=OptionsFlowOverlayConfig(expiration_filter="1DTE"))
    weekly = build_flow_bubbles(events, config=OptionsFlowOverlayConfig(expiration_filter="WEEKLY"))
    monthly = build_flow_bubbles(events, config=OptionsFlowOverlayConfig(expiration_filter="MONTHLY"))

    assert [bubble.strike for bubble in zero_dte] == [650]
    assert [bubble.strike for bubble in one_dte] == [651]
    assert [bubble.strike for bubble in weekly] == [652]
    assert [bubble.strike for bubble in monthly] == [653]
    assert monthly[0].expiration is not None


def test_flow_filters_by_custom_expiration_date():
    events = events_from_records([
        {
            "timestamp": "2026-09-18 10:00",
            "expiration": "2026-09-18",
            "strike": 650,
            "type": "C",
            "price": 10,
            "quantity": 10,
        },
        {
            "timestamp": "2026-09-18 10:00",
            "expiration": "2026-09-25",
            "strike": 652,
            "type": "C",
            "price": 10,
            "quantity": 10,
        },
    ], symbol="SPY", contract_multiplier=100)

    exact = build_flow_bubbles(events, config=OptionsFlowOverlayConfig(expiration_filter="2026-09-25"))
    custom = build_flow_bubbles(events, config=OptionsFlowOverlayConfig(expiration_filter="CUSTOM:2026-09-25"))
    invalid = build_flow_bubbles(events, config=OptionsFlowOverlayConfig(expiration_filter="CUSTOM"))

    assert [bubble.strike for bubble in exact] == [652]
    assert [bubble.strike for bubble in custom] == [652]
    assert invalid == []


def test_specific_expiration_filter_excludes_missing_expiration_without_crashing():
    events = events_from_records([
        {"timestamp": "2026-09-18 10:00", "strike": 650, "type": "C", "price": 10, "quantity": 10},
    ], symbol="SPY", contract_multiplier=100)

    all_bubbles = build_flow_bubbles(events, config=OptionsFlowOverlayConfig(expiration_filter="ALL"))
    zero_dte = build_flow_bubbles(events, config=OptionsFlowOverlayConfig(expiration_filter="0DTE"))

    assert len(all_bubbles) == 1
    assert zero_dte == []


def test_build_gex_levels_reuses_existing_level_outputs_and_chain_stats():
    chain = pd.DataFrame({
        "strike": [95.0, 100.0, 105.0],
        "type": ["P", "C", "C"],
        "gex": [-8_000_000.0, 3_000_000.0, 9_000_000.0],
        "open_interest": [500, 200, 400],
        "volume": [50, 20, 40],
    })

    levels = build_gex_levels(
        chain,
        101.0,
        100.0,
        {"call_wall": 105.0, "put_support": 95.0},
    )

    by_name = {level.name: level for level in levels}
    assert by_name["Call Wall"].price == 105.0
    assert by_name["Call Wall"].value == 9_000_000.0
    assert by_name["Call Wall"].open_interest == 400
    assert by_name["Put Wall"].volume == 50
    assert by_name["Gamma Flip"].style == "dash"
