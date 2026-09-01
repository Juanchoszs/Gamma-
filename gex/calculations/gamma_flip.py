from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from . import greeks
from ..infrastructure import rates
from ..config import CONTRACT_MULTIPLIER, SETTINGS
from ..domain import DataQuality
from ..domain.models import ChainSnapshot

ET = ZoneInfo("America/New_York")
YEAR_SECONDS = 365.0 * 24 * 3600
EXPIRY_BUCKETS = ["0DTE", "Semaine", "Mois", "Tout"]
def gamma_profile(df: pd.DataFrame, spot: float, weight_col: str = "open_interest",
                  range_pct: float | None = None, steps: int | None = None
                  ) -> tuple[np.ndarray, np.ndarray] | None:
    """Net GEX profile recalculated on a hypothetical spot grid.

    IV and maturities are fixed to isolate position effects.
    Slope near spot indicates regime degradation speed; troughs highlight acceleration zones.

    Returns (spot grid, net GEX in $ per 1%), or None.
    """
    d = df[(df["iv"] > 1e-4) & (df[weight_col] > 0)]
    if d.empty:
        return None
    rng = SETTINGS.zg_range if range_pct is None else range_pct
    n = SETTINGS.zg_steps if steps is None else steps
    grid = np.linspace(spot * (1 - rng), spot * (1 + rng), n)
    k = d["strike"].to_numpy()[:, None]
    t = d["t_years"].to_numpy()[:, None]
    iv = d["iv"].to_numpy()[:, None]
    oi = d[weight_col].to_numpy()[:, None]
    sign = np.where((d["type"] == "C").to_numpy()[:, None], 1.0, -1.0)
    g = greeks.gamma(grid[None, :], k, t, rates.current_rate(), iv)
    profile = (sign * g * oi * CONTRACT_MULTIPLIER * grid[None, :] ** 2 * 0.01).sum(axis=0)
    return grid, profile


def gex_at_spot(df: pd.DataFrame, ref_spot: float,
                weight_col: str = "open_interest") -> pd.Series:
    """GEX by strike, gamma RECALCULATED at a reference spot.

    Different from `gex_by_strike_weighted`, which uses feed spot gamma.
    Since gamma peaks at ATM, evaluating at live spot makes the strongest wall move with price.
    Evaluating at a fixed spot (prior close) keeps the walls stable intraday.
    """
    d = df[(df["iv"] > 1e-4) & (df[weight_col] > 0)]
    if d.empty:
        return pd.Series(dtype=float)
    g = greeks.gamma(ref_spot, d["strike"].to_numpy(), d["t_years"].to_numpy(),
                     rates.current_rate(), d["iv"].to_numpy())
    sign = np.where((d["type"] == "C").to_numpy(), 1.0, -1.0)
    gex = (sign * g * d[weight_col].to_numpy()
           * CONTRACT_MULTIPLIER * ref_spot ** 2 * 0.01)
    return pd.Series(gex, index=d["strike"].to_numpy()).groupby(level=0).sum()


def net_gex_at(df: pd.DataFrame, spot: float,
               weight_col: str = "open_interest") -> float | None:
    """Net GEX recalculated at a given spot, keeping IV/t fixed.

    Used to refresh live GEX when spot moves but OI is unchanged.
    Consistent with gamma flip calculation.
    """
    res = gamma_profile(df, spot, weight_col, range_pct=0.0, steps=1)
    return None if res is None else float(res[1][0])


def zero_gamma(df: pd.DataFrame, spot: float, weight_col: str = "open_interest") -> float | None:
    """Spot level where net GEX crosses zero.

    Recalculates BS gamma on a grid ±zg_range, keeping IV/t fixed, and interpolates crossing.
    `weight_col="open_interest"`: structural flip (classic zero gamma).
    `weight_col="volume"`: HVL volatility trigger (intraday hedging flip).
    """
    res = gamma_profile(df, spot, weight_col)
    if res is None:
        return None
    grid, profile = res
    crossings = np.where(np.diff(np.sign(profile)) != 0)[0]
    if len(crossings) == 0:
        return None
    # closest zero crossing to spot
    idx = crossings[np.argmin(np.abs(grid[crossings] - spot))]
    x0, x1 = grid[idx], grid[idx + 1]
    y0, y1 = profile[idx], profile[idx + 1]
    return float(x0 - y0 * (x1 - x0) / (y1 - y0))

