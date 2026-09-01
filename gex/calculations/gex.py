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
def seconds_to_expiry(expiries: pd.Series, now_et: datetime) -> np.ndarray:
    """Seconds to expiry (assumed 16:00 ET).

    Negative = expired (exclude).
    """
    expiry_dt = pd.to_datetime(expiries).dt.tz_localize(ET) + pd.Timedelta(hours=16)
    return (expiry_dt - now_et).dt.total_seconds().to_numpy()


def enrich(snapshot: ChainSnapshot, now_et: datetime | None = None) -> pd.DataFrame:
    """Add t, calculated greeks (BS on feed IV), GEX, and DEX.

    Falls back to CBOE greeks when IV is missing/zero.
    """
    now_et = now_et or datetime.now(ET)
    df = snapshot.options.copy()
    # Exclude expired contracts (incl. 0DTE after 16:00 ET)
    secs = seconds_to_expiry(df["expiry"], now_et)
    df = df[secs > 0].reset_index(drop=True)
    s = snapshot.spot
    # 5 min floor to avoid explosive gamma near close
    t = np.maximum(secs[secs > 0], 300.0) / YEAR_SECONDS
    iv = df["iv"].to_numpy()
    valid = iv > 1e-4

    r = rates.current_rate()
    g = np.where(valid, greeks.gamma(s, df["strike"], t, r, np.where(valid, iv, 1.0)), df["gamma_cboe"])
    d_call = greeks.call_delta(s, df["strike"], t, r, np.where(valid, iv, 1.0))
    is_call = (df["type"] == "C").to_numpy()
    d = np.where(valid, np.where(is_call, d_call, d_call - 1.0), df["delta_cboe"])

    df["t_years"] = t
    df["gamma_bs"] = g
    df["delta_bs"] = d

    oi = df["open_interest"].to_numpy()
    sign = np.where(is_call, 1.0, -1.0)
    df["gex"] = sign * g * oi * CONTRACT_MULTIPLIER * s**2 * 0.01
    # GEX assumes dealers long calls / short puts, so we flip signs to make calls/puts comparable.
    # DEX assumes dealers short calls AND short puts (selling upside, selling protection).
    # This means a uniform negation of raw delta, NOT a differential flip.
    # Result: Short call -> -δ_call (negative). Short put -> -δ_put = +|δ_put| (positive).
    # Net DEX matches GEX narrative: more puts -> dealers shorter puts -> longer delta -> positive Net DEX.
    df["dex"] = -1.0 * d * oi * CONTRACT_MULTIPLIER * s
    # Repeat spot on every row for self-contained persisted snapshots.
    df["spot"] = float(s)
    return df


def add_second_order(df: pd.DataFrame, spot: float) -> pd.DataFrame:
    """Add vanna/charm and their $ exposures.

    - vex: $ delta per 1% IV change.
    - cex: $ delta per elapsed day.
    """
    d = df.copy()
    valid = d["iv"] > 1e-4
    iv = np.where(valid, d["iv"].to_numpy(), 1.0)
    t = d["t_years"].to_numpy()
    k = d["strike"].to_numpy()
    r = rates.current_rate()
    v = greeks.vanna(spot, k, t, r, iv)
    c = greeks.charm_per_day(spot, k, t, r, iv)
    v = np.where(valid, v, 0.0)
    c = np.where(valid, c, 0.0)
    sign = np.where((d["type"] == "C").to_numpy(), 1.0, -1.0)
    oi = d["open_interest"].to_numpy()
    d["vanna"] = v
    d["charm"] = c
    d["vex"] = sign * v * 0.01 * oi * CONTRACT_MULTIPLIER * spot
    d["cex"] = sign * c * oi * CONTRACT_MULTIPLIER * spot
    return d


def bucket_mask(df: pd.DataFrame, bucket: str, today: date) -> pd.Series:
    if bucket == "0DTE":
        # Nearest expiry (true 0DTE in session, or next available session).
        if df.empty:
            return pd.Series(False, index=df.index)
        return df["expiry"] == df["expiry"].min()
    if bucket == "Semaine":
        return df["expiry"] <= today + timedelta(days=7)
    if bucket == "Mois":
        return df["expiry"] <= today + timedelta(days=35)
    return pd.Series(True, index=df.index)


def exposure_by_strike(df: pd.DataFrame, col: str) -> pd.DataFrame:
    """Aggregate gex/dex by strike, splitting calls/puts and net."""
    pivot = df.pivot_table(index="strike", columns="type", values=col, aggfunc="sum").fillna(0.0)
    for side in ("C", "P"):
        if side not in pivot:
            pivot[side] = 0.0
    pivot["net"] = pivot["C"] + pivot["P"]
    return pivot.reset_index()


def gex_by_strike_weighted(df: pd.DataFrame, spot: float,
                           weight_col: str = "open_interest") -> pd.Series:
    """GEX by strike, weighted by open interest or daily volume.

    OI shows established positioning, volume shows current session activity.
    Differences highlight intraday importance shifts.
    """
    if df.empty or weight_col not in df.columns:
        return pd.Series(dtype=float)
    sign = np.where((df["type"] == "C").to_numpy(), 1.0, -1.0)
    gex = (sign * df["gamma_bs"].to_numpy() * df[weight_col].to_numpy()
           * CONTRACT_MULTIPLIER * spot ** 2 * 0.01)
    return pd.Series(gex, index=df["strike"].to_numpy()).groupby(level=0).sum()

