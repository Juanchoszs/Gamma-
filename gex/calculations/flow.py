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
def put_call_ratios(df: pd.DataFrame) -> dict[str, float]:
    calls = df[df["type"] == "C"]
    puts = df[df["type"] == "P"]
    oi_c, oi_p = calls["open_interest"].sum(), puts["open_interest"].sum()
    v_c, v_p = calls["volume"].sum(), puts["volume"].sum()
    return {
        "pc_oi": float(oi_p / oi_c) if oi_c > 0 else float("nan"),
        "pc_volume": float(v_p / v_c) if v_c > 0 else float("nan"),
    }

def oi_change(prev: pd.DataFrame, cur: pd.DataFrame) -> pd.DataFrame:
    """Open interest change by strike between sessions.

    OI is published once daily (by OCC). The difference measures NET positioning changes, unlike residual gamma.
    Returns strike / d_call / d_put / d_net / oi_call / oi_put.
    """
    if prev is None or prev.empty or cur.empty:
        return pd.DataFrame()
    keys = ["strike", "type"]
    a = cur.groupby(keys)["open_interest"].sum().rename("cur")
    b = prev.groupby(keys)["open_interest"].sum().rename("prev")
    m = pd.concat([a, b], axis=1).fillna(0.0).reset_index()
    m["delta"] = m["cur"] - m["prev"]
    piv = m.pivot_table(index="strike", columns="type",
                        values=["delta", "cur"], aggfunc="sum").fillna(0.0)
    out = pd.DataFrame({"strike": piv.index})
    for side, name in (("C", "call"), ("P", "put")):
        out[f"d_{name}"] = piv["delta"][side].to_numpy() if side in piv["delta"] else 0.0
        out[f"oi_{name}"] = piv["cur"][side].to_numpy() if side in piv["cur"] else 0.0
    out["d_net"] = out["d_call"] - out["d_put"]
    return out.reset_index(drop=True)


def flow_delta(prev: pd.DataFrame, cur: pd.DataFrame, spot: float) -> dict[str, float]:
    """Delta flow proxy between pulls: Δvolume × delta × mult × spot.

    Taker direction (buy/sell) is unobservable in this feed; this is a volume-weighted proxy, not signed flow.
    """
    m = cur.merge(
        prev[["contract", "volume"]].rename(columns={"volume": "volume_prev"}),
        on="contract",
        how="left",
    )
    dvol = (m["volume"] - m["volume_prev"].fillna(0.0)).clip(lower=0.0)
    signed = dvol * m["delta_bs"] * CONTRACT_MULTIPLIER * spot
    is_call = m["type"] == "C"
    today = datetime.now(ET).date()

    # Exchanged gamma: GEX formula weighted by volume instead of OI.
    # Shows if traded volume adds stabilizing (calls) or destabilizing (puts) gamma.
    # Acts as a "CVD" of gamma.
    gsign = np.where(is_call, 1.0, -1.0)
    gsigned = (dvol * m["gamma_bs"] * gsign
               * CONTRACT_MULTIPLIER * spot ** 2 * 0.01)
    return {
        "flow_total": float(signed.sum()),
        "flow_calls": float(signed[is_call].sum()),
        "flow_puts": float(signed[~is_call].sum()),
        "flow_0dte": float(signed[m["expiry"] == today].sum()),
        # calls positive, puts negative: sum is net
        "gflow_total": float(gsigned.sum()),
        "gflow_calls": float(gsigned[is_call].sum()),
        "gflow_puts": float(gsigned[~is_call].sum()),
        "gflow_0dte": float(gsigned[m["expiry"] == today].sum()),
        "contracts_traded": float(dvol.sum()),
        "source": "cboe",   # direct from public source
    }