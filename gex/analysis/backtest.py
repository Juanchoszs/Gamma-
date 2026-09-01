"""Backtest levels: did a level hold, break, and how far did price then move?

The core consists of pure functions taking (level, price path): they read no
files, making them testable with hand-built paths and reusable with any source
—local snapshots, Databento reconstruction, or future sources.

Three methodological safeguards determine result validity far more than code:

1. **Test levels are from the START of the session.** Open interest is published
   in the morning; using closing levels would test unknown information and
   artificially inflate success rates.

2. **A level never approached did not “hold.”** Hold rate is meaningful only
   across sessions where price actually reached the level; otherwise a distant
   level could show 100% success without demonstrating anything.

3. **Touching is not breaking.** A one-tick overshoot is not a break: a margin
   is required, otherwise quote noise turns every touch into a break.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from .. import metrics, store

# Overshoot margin required to count as a break, expressed as a price fraction.
#
# An initial version used 0.05% to filter quote noise. Across 22 SPX sessions,
# median overshoot of a tested level was 0.24%; at 0.05%, nearly every touch
# counted as a break and the break rate reached 90%. Noise filtering and break
# definition are distinct requirements.
#
# 0.15% (about 11 points on SPX at 7400) remains above noise while requiring a
# clear crossing. The threshold is still conventional; `close_beyond`, which
# has no tuning parameter, is the most robust measure of level failure.
BREAK_TOL = 0.0015


@dataclass(frozen=True)
class LevelOutcome:
    day: str
    symbol: str
    name: str
    level: float
    side: str            # "resistance" (above the open) or "support"
    tested: bool         # price reached the level
    broke: bool          # clear overshoot beyond BREAK_TOL
    closed_beyond: bool  # session ended on the other side
    excursion_pct: float # maximum overshoot beyond the level, in %
    move_after_break_pct: float | None  # move beyond the level after breaking


def evaluate_level(name: str, level: float, path: np.ndarray, open_px: float,
                   day: str = "", symbol: str = "",
                   tol: float = BREAK_TOL) -> LevelOutcome:
    """Compare a level with a session's price path.

    `path`: prices ordered in time (the first is the open).
    """
    side = "resistance" if level >= open_px else "support"
    margin = level * tol

    if side == "resistance":
        tested = bool(np.any(path >= level))
        broken = path >= level + margin
        beyond = (path.max() - level) / level if tested else 0.0
        closed_beyond = bool(path[-1] > level)
    else:
        tested = bool(np.any(path <= level))
        broken = path <= level - margin
        beyond = (level - path.min()) / level if tested else 0.0
        closed_beyond = bool(path[-1] < level)

    broke = bool(np.any(broken))
    move_after = None
    if broke:
        # Measure the furthest move from the first break onward.
        i = int(np.argmax(broken))
        rest = path[i:]
        move_after = float((rest.max() - level) / level if side == "resistance"
                           else (level - rest.min()) / level)

    return LevelOutcome(
        day=day, symbol=symbol, name=name, level=float(level), side=side,
        tested=tested, broke=broke, closed_beyond=closed_beyond,
        excursion_pct=float(max(beyond, 0.0)),
        move_after_break_pct=move_after,
    )


def evaluate_session(levels: dict[str, float], path: np.ndarray,
                     day: str = "", symbol: str = "") -> list[LevelOutcome]:
    """Evaluate all session levels against its price path."""
    if len(path) < 2:
        return []
    open_px = float(path[0])
    return [evaluate_level(n, lv, path, open_px, day, symbol)
            for n, lv in levels.items() if lv is not None and np.isfinite(lv)]


def summarize(outcomes: list[LevelOutcome] | pd.DataFrame) -> pd.DataFrame:
    """Aggregate by level type: test, hold, and break frequency.

    Hold rate is conditional on a test (see safeguard 2): `n_tested` shows how
    many sessions support the calculation. A value based on two or three
    sessions is not meaningful; the column makes that visible.
    """
    df = (pd.DataFrame([asdict(o) for o in outcomes])
          if not isinstance(outcomes, pd.DataFrame) else outcomes)
    if df.empty:
        return pd.DataFrame(columns=["name", "n_sessions", "n_tested",
                                     "test_rate", "hold_rate", "break_rate",
                                     "close_beyond_rate", "median_move_after_break"])
    rows = []
    for name, g in df.groupby("name", sort=False):
        tested = g[g["tested"]]
        n_t = len(tested)
        rows.append({
            "name": name,
            "n_sessions": len(g),
            "n_tested": n_t,
            "test_rate": len(tested) / len(g),
            # Hold means tested without a clear break.
            "hold_rate": float((~tested["broke"]).mean()) if n_t else np.nan,
            "break_rate": float(tested["broke"].mean()) if n_t else np.nan,
            "close_beyond_rate": float(tested["closed_beyond"].mean()) if n_t else np.nan,
            "median_move_after_break": float(
                tested["move_after_break_pct"].dropna().median())
            if tested["move_after_break_pct"].notna().any() else np.nan,
        })
    return pd.DataFrame(rows)


# --------------------------------------------------------------- adaptateurs
def session_levels(symbol: str, day: str, spot: float | None = None) -> dict[str, float]:
    """Session-start levels, recalculated from the first snapshot.

    `spot` may be supplied by the caller: older snapshots do not contain the
    column, and the first session price works just as well.

    If no snapshot exists for that day, use the LAST snapshot from the previous
    session. This is not a compromise: morning open interest reflects the prior
    close, so these are exactly the levels visible at the open. It also makes
    Databento-reconstructed close snapshots usable.
    """
    df = store.load_first_snapshot(symbol, day)
    if df is None or df.empty:
        prev = store.load_previous_snapshot(symbol, day)
        df = prev[1] if prev else None
    if df is None or df.empty:
        return {}
    if spot is None and "spot" in df.columns:
        spot = float(df["spot"].iloc[0])
    out: dict[str, float] = {}
    # Evaluate walls at the prior close, as in the dashboard; otherwise the
    # backtest would test levels the tool never displayed.
    ref = store.previous_close_spot(symbol, day) or spot
    if spot is not None:
        keys = metrics.key_levels(df, spot, ref_spot=ref)
        out.update({k: v for k, v in keys.items() if v is not None})
        zg = metrics.zero_gamma(df, spot)
        if zg is not None:
            out["gamma_flip"] = zg
    lv = metrics.top_gex_levels(df, ref_spot=ref)
    for row in lv.itertuples():
        out[f"GEX{row.rank}"] = float(row.strike)
    return out


def session_path(symbol: str, day: str) -> np.ndarray:
    """Return the price path for a session.

    Two sources, in order of preference:

    1. **1-minute bars** from the real-time feed: extremes are exact, so a wick
       touching a level is captured. This is the only resolution that measures
       break rates honestly.
    2. **Metrics history** (one point per snapshot, about 10 minutes): fallback
       when bars are missing. Wicks disappear, so resulting rates are a floor,
       never a measurement.

    Bars are expanded to open/high/low/close so `evaluate_level` sees extremes.
    High-then-low order within a minute is a convention (the actual order is
    unknown) and does not affect calculated indicators.
    """
    px = store.load_prices(symbol, day)
    if not px.empty:
        px = px.sort_values("timestamp")
        return px[["open", "high", "low", "close"]].to_numpy(dtype=float).ravel()
    h = store.load_history(symbol)
    if h.empty:
        return np.array([])
    ts = pd.to_datetime(h["timestamp"])
    sel = h[ts.dt.strftime("%Y-%m-%d") == day].sort_values("timestamp")
    return sel["spot"].to_numpy(dtype=float)


def path_resolution(symbol: str, day: str) -> str:
    """Return the actual session resolution used for the result."""
    return "1min" if not store.load_prices(symbol, day).empty else "snapshot"


def run(symbol: str, days: list[str] | None = None) -> pd.DataFrame:
    """Backtest every session with both levels and prices.

    Candidate days are those with a price path; levels may come from the
    previous session (see `session_levels`). Restricting to days with a
    snapshot would omit otherwise testable sessions.
    """
    days = days or sorted(set(store.price_days(symbol))
                          | set(store.snapshot_days(symbol)))
    outcomes: list[dict] = []
    for day in days:
        path = session_path(symbol, day)
        if len(path) < 2:
            continue
        levels = session_levels(symbol, day, spot=float(path[0]))
        if not levels:
            continue
        res = path_resolution(symbol, day)
        for o in evaluate_session(levels, path, day, symbol):
            outcomes.append({**asdict(o), "resolution": res})
    return pd.DataFrame(outcomes)
