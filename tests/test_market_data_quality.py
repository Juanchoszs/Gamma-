from __future__ import annotations

import pandas as pd

from gex.application.market_intelligence import inspect_option_data_quality, valid_option_records


def test_option_data_quality_reports_invalid_and_missing_fields_without_mutating_chain():
    chain = pd.DataFrame({
        "strike": [100.0, 100.0, -1.0, 110.0],
        "type": ["C", "C", "P", "X"],
        "expiry": ["2026-09-18", "2026-09-18", None, "not-a-date"],
        "gamma": [1.0, None, 1.0, 1.0],
        "delta": [0.5, 0.5, None, 0.5],
        "iv": [0.2, 0.2, 0.2, None],
        "open_interest": [100, None, 20, 10],
        "volume": [10, 5, None, 1],
    })

    quality = inspect_option_data_quality(chain)

    assert quality.record_count == 4
    assert quality.valid_record_count == 2
    assert quality.invalid_record_count == 2
    assert quality.missing_greeks == 3
    assert quality.missing_open_interest == 1
    assert quality.missing_volume == 1
    assert quality.missing_expiration == 1
    assert quality.invalid_timestamps == 1
    assert quality.duplicate_contracts == 2


def test_valid_option_records_excludes_only_structurally_invalid_contracts():
    chain = pd.DataFrame({
        "strike": [100.0, 0.0, 105.0],
        "type": ["C", "P", "X"],
        "expiry": ["2026-09-18", "2026-09-18", "bad-date"],
        "gamma": [None, 1.0, 1.0],
    })

    valid = valid_option_records(chain)

    assert list(valid.index) == [0]
    assert pd.isna(valid.iloc[0]["gamma"])
