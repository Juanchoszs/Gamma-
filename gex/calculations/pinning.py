"""Derived closing-pinning metrics for option strikes and GEX walls."""
from __future__ import annotations

import numpy as np
import pandas as pd


def strike_spacing(strikes) -> float | None:
    """Return the median positive distance between unique strikes."""
    s = np.sort(np.unique(np.asarray(list(strikes), dtype=float)))
    if len(s) < 2:
        return None
    diffs = np.diff(s)
    diffs = diffs[diffs > 0]
    return float(np.median(diffs)) if len(diffs) else None


def top_walls(chain_df: pd.DataFrame, n: int = 2) -> list[tuple[float, float]]:
    """Return the strikes with the largest absolute aggregated GEX."""
    by = chain_df.groupby("strike")["gex"].sum()
    order = by.abs().sort_values(ascending=False).index
    return [(float(k), float(by[k])) for k in order[:n]]


def _dist(a, b):
    return round(abs(a - b), 2) if a is not None and b is not None else None


def pin_metrics(chain_df: pd.DataFrame, close_price: float,
                window_closes: list[float] | None = None) -> dict:
    """Return pinning metrics for a closing price and optional pre-close path."""
    strikes = sorted(float(s) for s in pd.unique(chain_df["strike"]))
    spacing = strike_spacing(strikes)
    nearest = min(strikes, key=lambda k: abs(k - close_price)) if strikes else None
    dist_ns = _dist(close_price, nearest)
    pin_ratio = (round(dist_ns / (spacing / 2), 3)
                 if dist_ns is not None and spacing else None)

    walls = top_walls(chain_df, 2)
    gex1 = walls[0][0] if len(walls) > 0 else None
    gex2 = walls[1][0] if len(walls) > 1 else None

    crossings = None
    if window_closes and spacing:
        idx = [int(round(c / spacing)) for c in window_closes]
        crossings = int(sum(abs(idx[i + 1] - idx[i]) for i in range(len(idx) - 1)))

    return {
        "close": round(float(close_price), 2),
        "nearest_strike": nearest,
        "dist_nearest_strike": dist_ns,
        "strike_spacing": spacing,
        "pin_ratio": pin_ratio,
        "closing_strike": nearest,
        "gex1_strike": gex1, "dist_gex1": _dist(close_price, gex1),
        "gex2_strike": gex2, "dist_gex2": _dist(close_price, gex2),
        "strike_crossings_preclose": crossings,
    }
