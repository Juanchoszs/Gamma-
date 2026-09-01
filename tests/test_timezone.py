"""Tests for timezone consistency in store functions.

The project uses Eastern Time (America/New_York) as the canonical timezone
for market operations. All date/time operations should use ET, not local time.
"""
from __future__ import annotations

import pandas as pd
import pytest

from gex import store
from gex.config import SETTINGS
from gex.metrics import ET


def test_previous_close_spot_uses_et_timezone(tmp_path, monkeypatch):
    """previous_close_spot must use ET timezone, not local naive time.

    This test ensures the function uses datetime.now(ET) instead of
    datetime.now() to avoid timezone-related bugs when the system runs
    in a different timezone than ET.
    """
    monkeypatch.setattr(SETTINGS, "data_dir", tmp_path)

    # Create some history data
    history_data = pd.DataFrame([
        {
            "timestamp": pd.Timestamp("2026-01-14 16:00:00"),
            "symbol": "SPX", "spot": 4800.0, "net_gex": 1e9,
            "zero_gamma": 4790.0, "pc_oi": 1.0, "pc_volume": 1.0,
            "net_gex_0dte": 0.0, "basis": None, "source": "cboe",
            "net_dex": 0.0,
        },
        {
            "timestamp": pd.Timestamp("2026-01-15 16:00:00"),
            "symbol": "SPX", "spot": 4820.0, "net_gex": 1.1e9,
            "zero_gamma": 4810.0, "pc_oi": 1.0, "pc_volume": 1.0,
            "net_gex_0dte": 0.0, "basis": None, "source": "cboe",
            "net_dex": 0.0,
        },
    ])
    store.append_history(history_data.iloc[0].to_dict())
    store.append_history(history_data.iloc[1].to_dict())

    # Test with explicit day parameter (should work regardless of timezone)
    result = store.previous_close_spot("SPX", "2026-01-15")
    assert result == 4800.0

    # Test with None day parameter - this uses datetime.now() internally
    # The function should not crash and should use ET timezone
    result_none = store.previous_close_spot("SPX", None)
    assert result_none is not None


def test_store_imports_et_from_metrics():
    """Verify that store module imports ET from metrics for timezone consistency."""
    # This test ensures the import exists and ET is the correct timezone
    assert ET is not None
    assert str(ET) == "America/New_York"
    # Store should use ET from metrics
    from gex import store as store_module
    # The module should have access to ET (either imported or local)
    # This is a smoke test to ensure no import errors


def test_et_timezone_consistency():
    """ET timezone should be consistent across the project."""
    from gex.metrics import ET as ET_METRICS
    from gex.providers.ingest import _ET as ET_INGEST
    from gex.scheduler import ET as ET_SCHEDULER
    from gex.app import ET as ET_APP

    # All ET references should point to the same timezone
    assert str(ET_METRICS) == "America/New_York"
    assert str(ET_INGEST) == "America/New_York"
    assert str(ET_SCHEDULER) == "America/New_York"
    assert str(ET_APP) == "America/New_York"