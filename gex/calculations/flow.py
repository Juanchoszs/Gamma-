from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from .. import greeks, rates
from ..config import CONTRACT_MULTIPLIER, SETTINGS
from ..domain import DataQuality
from ..ingest import ChainSnapshot

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
    """Variation d'open interest par strike entre deux séances.

    L'OI n'est publié qu'une fois par jour (matin, par l'OCC) : la différence
    entre deux séances mesure le positionnement NET réellement ouvert ou
    fermé, à distinguer du gamma résiduel hérité de positions anciennes.

    Retourne un DataFrame strike / d_call / d_put / d_net / oi_call / oi_put.
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
    """Proxy de flux delta entre deux pulls : Δvolume × delta × mult × spot.

    Le sens taker (achat/vente) n'est pas observable dans ce feed : c'est un
    proxy de pression delta-pondérée, pas un vrai order-flow signé.
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

    # Gamma échangé sur l'intervalle : même formule que le GEX, mais pondérée
    # par le volume du pas de temps au lieu de l'open interest. Cumulé sur la
    # séance, cela montre si ce qui se traite ajoute du gamma stabilisant
    # (calls) ou déstabilisant (puts) — un « CVD » du gamma.
    gsign = np.where(is_call, 1.0, -1.0)
    gsigned = (dvol * m["gamma_bs"] * gsign
               * CONTRACT_MULTIPLIER * spot ** 2 * 0.01)
    return {
        "flow_total": float(signed.sum()),
        "flow_calls": float(signed[is_call].sum()),
        "flow_puts": float(signed[~is_call].sum()),
        "flow_0dte": float(signed[m["expiry"] == today].sum()),
        # gflow_calls est positif, gflow_puts négatif : leur somme est le net
        "gflow_total": float(gsigned.sum()),
        "gflow_calls": float(gsigned[is_call].sum()),
        "gflow_puts": float(gsigned[~is_call].sum()),
        "gflow_0dte": float(gsigned[m["expiry"] == today].sum()),
        "contracts_traded": float(dvol.sum()),
        "source": "cboe",   # collecté en direct sur la source publique
    }