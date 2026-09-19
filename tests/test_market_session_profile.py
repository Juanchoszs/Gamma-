from __future__ import annotations

from datetime import datetime

import pandas as pd

from gex.application.market_intelligence.session_profile import (
    SessionProfileConfig,
    build_session_levels_from_profile,
    build_session_profile_payload,
)


def _prices() -> pd.DataFrame:
    return pd.DataFrame({
        "timestamp": [
            "2026-09-17 16:05:00",
            "2026-09-17 20:00:00",
            "2026-09-18 09:00:00",
            "2026-09-18 09:30:00",
            "2026-09-18 09:31:00",
            "2026-09-18 09:32:00",
        ],
        "open": [7588.0, 7590.0, 7591.0, 7592.0, 7594.0, 7593.0],
        "high": [7590.0, 7592.0, 7594.0, 7595.0, 7596.0, 7595.0],
        "low": [7587.0, 7589.0, 7590.0, 7591.0, 7592.0, 7591.0],
        "close": [7589.0, 7591.0, 7593.0, 7594.0, 7595.0, 7592.0],
        "volume": [100.0, 300.0, 200.0, 500.0, 1_000.0, 250.0],
    })


def test_session_profile_payload_builds_regular_and_overnight_levels():
    payload = build_session_profile_payload(
        symbol="SPX",
        timestamp=datetime(2026, 9, 18, 9, 32),
        prices=_prices(),
        config=SessionProfileConfig(price_bin_size=1.0),
    )

    assert payload["symbol"] == "SPX"
    assert payload["timezone"] == "America/New_York"
    regular = payload["sessions"]["regular"]
    assert regular["available"] is True
    assert regular["bar_count"] == 3
    assert regular["weight"] == "volume"
    assert regular["levels"]["open"] == 7592.0
    assert regular["levels"]["high"] == 7596.0
    assert regular["levels"]["low"] == 7591.0
    assert regular["levels"]["close"] == 7592.0
    assert regular["levels"]["poc"] == 7595.0
    assert regular["levels"]["vah"] >= regular["levels"]["val"]

    overnight = payload["sessions"]["overnight"]
    assert overnight["available"] is True
    assert overnight["bar_count"] == 3
    assert overnight["levels"]["high"] == 7594.0
    assert overnight["levels"]["low"] == 7587.0


def test_session_profile_levels_preserve_origin_and_session():
    payload = build_session_profile_payload(
        symbol="SPX",
        timestamp=datetime(2026, 9, 18, 9, 32),
        prices=_prices(),
        config=SessionProfileConfig(price_bin_size=1.0),
    )

    levels = build_session_levels_from_profile(payload)

    level_types = {(level.session.value, level.level_type.value) for level in levels}
    assert ("REGULAR", "POC") in level_types
    assert ("REGULAR", "VAH") in level_types
    assert ("REGULAR", "VAL") in level_types
    assert ("OVERNIGHT", "OVH") in level_types
    assert ("OVERNIGHT", "OVL") in level_types
    poc = next(level for level in levels if level.id.startswith("REGULAR-POC"))
    assert poc.source.value == "SESSION_PROFILE"
    assert poc.metadata["profile_key"] == "poc"
    assert 0 <= poc.strength <= 100


def test_session_profile_payload_marks_missing_bars_unavailable():
    payload = build_session_profile_payload(
        symbol="SPX",
        timestamp=datetime(2026, 9, 18, 9, 32),
        prices=pd.DataFrame(),
    )

    assert payload["sessions"]["regular"]["available"] is False
    assert payload["sessions"]["regular"]["levels"] == {}
    assert payload["sessions"]["overnight"]["available"] is False
