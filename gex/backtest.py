"""Backward compatibility: gex.backtest -> gex.analysis.backtest"""
from __future__ import annotations

from .analysis.backtest import (
    BREAK_TOL,
    LevelOutcome,
    evaluate_level,
    evaluate_session,
    summarize,
    session_levels,
    session_path,
    path_resolution,
    run,
)

__all__ = [
    "BREAK_TOL",
    "LevelOutcome",
    "evaluate_level",
    "evaluate_session",
    "summarize",
    "session_levels",
    "session_path",
    "path_resolution",
    "run",
]