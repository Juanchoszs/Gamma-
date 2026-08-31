"""C3 scheduler extraction: public API and module boundaries stay intact."""
from __future__ import annotations

from unittest.mock import patch

from gex import scheduler, state
from gex.application import flush_streams, refresh_market, refresh_native
from gex.calculations.native import build_native_summary as calc_native_summary
from gex.infrastructure.git_repository import push_data_repo as git_push


def test_compatibility_facades_point_at_extracted_callables():
    assert scheduler.STATE is state.STATE
    assert scheduler.pull_all is refresh_market.pull_all
    assert scheduler.pull_symbol is refresh_market.pull_symbol
    assert scheduler.pull_vix is refresh_market.pull_vix
    assert scheduler.pull_native_options is refresh_native.pull_native_options
    assert scheduler.pull_native_index is refresh_native.pull_native_index
    assert scheduler.native_index_key is refresh_native.native_index_key
    assert scheduler.flush_prices is flush_streams.flush_prices
    assert scheduler.flush_tape is flush_streams.flush_tape
    assert scheduler.flush_ticks is flush_streams.flush_ticks
    assert scheduler.build_native_summary is calc_native_summary
    assert scheduler.push_data_repo is git_push
    assert scheduler.NATIVE_CACHE_FRESH_S == refresh_native.NATIVE_CACHE_FRESH_S


def test_native_index_key_is_storage_not_calculation():
    assert refresh_native.native_index_key("SPX") == "SPX_RT"
    assert refresh_native.native_index_key("SPX") != "SPX"


def test_push_data_repo_skips_without_git(tmp_path, monkeypatch):
    from gex.config import SETTINGS

    monkeypatch.setattr(SETTINGS, "data_dir", tmp_path)
    monkeypatch.setattr(SETTINGS, "auto_push_data", True)
    git_push()  # no .git directory — must no-op without raising


def test_push_data_repo_disabled(tmp_path, monkeypatch):
    from gex.config import SETTINGS

    monkeypatch.setattr(SETTINGS, "data_dir", tmp_path)
    monkeypatch.setattr(SETTINGS, "auto_push_data", False)
    (tmp_path / ".git").mkdir()
    with patch("gex.infrastructure.git_repository.subprocess.run") as run:
        git_push()
    run.assert_not_called()


def test_start_scheduler_still_exported():
    assert callable(scheduler.start_scheduler)
    assert callable(scheduler.market_is_open)
    assert scheduler._Cadence is not None
