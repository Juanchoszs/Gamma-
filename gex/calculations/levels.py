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
from .gamma_flip import gex_at_spot
from .gex import bucket_mask

def third_friday(year: int, month: int) -> date:
    """3rd Friday of the month (CME index futures expiry)."""
    first = date(year, month, 1)
    return first + timedelta(days=(4 - first.weekday()) % 7 + 14)


def front_futures_expiry(today: date) -> date:
    """Front month future expiry (quarterly)."""
    for y in (today.year, today.year + 1):
        for m in (3, 6, 9, 12):
            e = third_friday(y, m)
            if e >= today:
                return e
    raise ValueError("expiry not found")


def futures_basis(df: pd.DataFrame, spot: float, today: date | None = None) -> float | None:
    """Future-spot basis from call-put parity: F = (C-P)·e^(rT) + K.

    Uses options nearest to front month future expiry and near-the-money median.
    Returns None if no valid pairs.
    Basis shrinks towards 0 near expiry; recalculated on every pull.
    """
    if df.empty:
        return None
    today = today or datetime.now(ET).date()
    target_exp = front_futures_expiry(today)
    exps = df["expiry"].unique()
    if len(exps) == 0:
        return None
    target = min(exps, key=lambda e: abs((e - target_exp).days))

    e = df[df["expiry"] == target]
    # Handle multiple roots (SPX/SPXW) on same expiry: keep most traded
    e = e.sort_values("volume").drop_duplicates(["type", "strike"], keep="last")
    calls = e[e["type"] == "C"].set_index("strike")
    puts = e[e["type"] == "P"].set_index("strike")
    common = [k for k in calls.index.intersection(puts.index)
              if abs(k - spot) / spot < 0.05]
    fwds = []
    for k in common:
        cmid = (calls.loc[k, "bid"] + calls.loc[k, "ask"]) / 2
        pmid = (puts.loc[k, "bid"] + puts.loc[k, "ask"]) / 2
        if cmid <= 0 or pmid <= 0:
            continue
        t = calls.loc[k, "t_years"]
        fwds.append((cmid - pmid) * np.exp(rates.current_rate() * t) + k)
    if len(fwds) < 5:
        return None
    basis = float(np.median(fwds)) - spot
    # Guardrail: index future basis stays under ~2% of spot.
    # Beyond this, quotes are aberrant and would skew all levels.
    if abs(basis) > 0.02 * spot:
        log.warning("Aberrant basis ignored: %+.1f pts on spot %.0f (%d pairs)",
                    basis, spot, len(fwds))
        return None
    return basis


def top_gex_levels(df: pd.DataFrame, n: int = 5,
                   ref_spot: float | None = None,
                   all_expiries: bool = False) -> pd.DataFrame:
    """Top n strikes by absolute GEX.

    Default is nearest expiry (0DTE in session). `all_expiries=True` aggregates all.
    `ref_spot` freezes the spot for gamma evaluation (usually prior close).
    Without it, gamma drifts with current price.

    Returns strike, net gex, rank (1 = strongest), and expiry.
    """
    if df.empty:
        return pd.DataFrame()
    nearest = df["expiry"].min()
    sub = df if all_expiries else df[df["expiry"] == nearest]
    if ref_spot:
        agg = gex_at_spot(sub, ref_spot).rename("gex").reset_index()
        agg = agg.rename(columns={"index": "strike"})
    else:
        agg = sub.groupby("strike")["gex"].sum().reset_index()
    agg = agg.loc[agg["gex"].abs().nlargest(n).index]
    agg = agg.sort_values("gex", key=abs, ascending=False).reset_index(drop=True)
    agg["rank"] = agg.index + 1
    agg["expiry"] = nearest
    return agg


def expected_move(df: pd.DataFrame, spot: float) -> float | None:
    """Expected move on nearest expiry via ATM straddle.

    The ATM straddle price is the market's expected move without model assumptions.
    Used for 1D Min / 1D Max bounds.
    """
    if df.empty:
        return None
    nearest = df["expiry"].min()
    e = df[df["expiry"] == nearest]
    e = e.sort_values("volume").drop_duplicates(["type", "strike"], keep="last")
    calls = e[e["type"] == "C"].set_index("strike")
    puts = e[e["type"] == "P"].set_index("strike")
    common = calls.index.intersection(puts.index)
    if len(common) == 0:
        return None
    k_atm = min(common, key=lambda k: abs(k - spot))

    def _price(side: pd.DataFrame) -> float | None:
        """Mid price, fallback to close.

        Databento chains lack bid/ask; they are closing snapshots where settlement price is used.
        Straddle remains computable.
        """
        row = side.loc[k_atm]
        if "bid" in side.columns and "ask" in side.columns:
            mid = (row["bid"] + row["ask"]) / 2
            if mid > 0:
                return float(mid)
        close = row.get("close")
        return float(close) if close is not None and close > 0 else None

    cmid, pmid = _price(calls), _price(puts)
    if not cmid or not pmid:
        return None
    move = float(cmid + pmid)
    # Guardrail: >10% expected move on front expiry implies aberrant quotes (unless crash).
    return move if 0 < move < 0.10 * spot else None


def key_levels(df: pd.DataFrame, spot: float,
               ref_spot: float | None = None,
               all_expiries: bool = False) -> dict[str, float | None]:
    """Directional levels:

    - call_wall: highest call gamma concentration ABOVE spot (resistance)
    - put_support: highest put gamma concentration BELOW spot (support)
    - d1_max/d1_min: expected move bounds (ATM straddle)

    Unlike GEX1-5, these are only searched on the side where they make sense.
    Default is nearest expiry; `all_expiries=True` aggregates all.
    """
    out: dict[str, float | None] = {
        "call_wall": None, "put_support": None, "d1_min": None, "d1_max": None,
    }
    if df.empty:
        return out
    nearest = df["expiry"].min()
    sub = df if all_expiries else df[df["expiry"] == nearest]
    # Wall RANKING uses reference spot (frozen structure);
    # Wall DIRECTION (above/below) uses CURRENT spot, since resistance only makes sense above market.
    agg = gex_at_spot(sub, ref_spot) if ref_spot else sub.groupby("strike")["gex"].sum()

    above = agg[(agg.index >= spot) & (agg > 0)]
    if len(above):
        out["call_wall"] = float(above.idxmax())
    below = agg[(agg.index <= spot) & (agg < 0)]
    if len(below):
        out["put_support"] = float(below.idxmin())

    move = expected_move(df, spot)
    if move is not None:
        out["d1_min"] = spot - move
        out["d1_max"] = spot + move
    return out


def compute_levels(chain: pd.DataFrame, structural_spot: float, live_spot: float,
                   bucket: str = "0DTE", today: date | None = None,
                   n: int = 5) -> dict:
    """SINGLE ENTRY POINT for displayed levels (GEX1-5 walls + call/put wall).

    Dashboard, API, and bot all call this to ensure consistency on reference spot and expiries.

    - `structural_spot`: frozen spot (prior close) -> wall **magnitude**
    - `live_spot`: current spot -> wall **side** (above/below = resistance/support)
    - `bucket`: expiry filter (0DTE/Week/Month/All)

    Returns {"levels": GEX1-n DataFrame, "keys": call_wall/put_support/1D dict}.
    """
    today = today or datetime.now(ET).date()
    sub = chain[bucket_mask(chain, bucket, today)] if not chain.empty else chain
    return {
        "levels": top_gex_levels(sub, n=n, ref_spot=structural_spot, all_expiries=True),
        "keys": key_levels(sub, live_spot, ref_spot=structural_spot, all_expiries=True),
    }
