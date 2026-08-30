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
from .gamma_flip import gex_at_spot
from .gex import bucket_mask

def third_friday(year: int, month: int) -> date:
    """3e vendredi du mois — échéance des futures index CME."""
    first = date(year, month, 1)
    return first + timedelta(days=(4 - first.weekday()) % 7 + 14)


def front_futures_expiry(today: date) -> date:
    """Échéance du future front month (trimestriel : mars/juin/sept/déc)."""
    for y in (today.year, today.year + 1):
        for m in (3, 6, 9, 12):
            e = third_friday(y, m)
            if e >= today:
                return e
    raise ValueError("échéance introuvable")


def futures_basis(df: pd.DataFrame, spot: float, today: date | None = None) -> float | None:
    """Basis future - spot, déduit de la parité call-put : F = (C-P)·e^(rT) + K.

    Utilise l'échéance d'options la plus proche de celle du future front month,
    et la médiane sur les strikes proches de la monnaie (robuste aux quotes
    aberrantes). Retourne None si aucune paire exploitable.

    Le basis décroît vers 0 à l'approche de l'échéance : il est recalculé à
    chaque pull, jamais figé.
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
    # racines multiples (SPX/SPXW) sur une même échéance : garder le plus traité
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
    # garde-fou : le basis d'un future index reste sous ~2 % du spot (portage
    # taux - dividendes sur < 1 an). Au-delà, les quotes sont aberrantes et une
    # conversion silencieuse fausserait tous les niveaux.
    if abs(basis) > 0.02 * spot:
        log.warning("Basis aberrant ignoré : %+.1f pts sur spot %.0f (%d paires)",
                    basis, spot, len(fwds))
        return None
    return basis


def top_gex_levels(df: pd.DataFrame, n: int = 5,
                   ref_spot: float | None = None,
                   all_expiries: bool = False) -> pd.DataFrame:
    """Les n strikes au |GEX| le plus fort.

    Par défaut sur l'échéance la plus proche (le 0DTE en séance ; la prochaine
    séance après la cloche). `all_expiries=True` agrège TOUTES les échéances du
    df fourni — c'est le point d'entrée `compute_levels` qui fixe alors le
    périmètre en amont (par bucket).

    `ref_spot` fige le spot auquel le gamma est évalué — la clôture de la
    veille, quand l'open interest a été arrêté. Sans lui, le gamma est repris
    du dernier pull et les murs se déplacent avec le prix (cf. `gex_at_spot`).

    Retourne strike, gex net, rang (1 = mur le plus fort) et l'expiration utilisée.
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
    """Move attendu sur l'échéance la plus proche, via le straddle ATM.

    Le prix du straddle à la monnaie EST l'estimation de move du marché, sans
    hypothèse de modèle. Sert de bornes 1D Min / 1D Max (façon MenthorQ).
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
        """Milieu de fourchette, à défaut le close.

        Les chaînes reconstruites depuis Databento ne portent pas de bid/ask :
        ce sont des photos de clôture, où le prix de règlement tient lieu de
        valorisation. Le straddle y reste calculable.
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
    # garde-fou : un move attendu > 10 % du spot sur l'échéance front est
    # incohérent hors krach — quotes probablement aberrantes.
    return move if 0 < move < 0.10 * spot else None


def key_levels(df: pd.DataFrame, spot: float,
               ref_spot: float | None = None,
               all_expiries: bool = False) -> dict[str, float | None]:
    """Niveaux directionnels (esprit MenthorQ) :

    - call_wall  : plus forte concentration de gamma call AU-DESSUS du spot
                   (résistance)
    - put_support: plus forte concentration de gamma put SOUS le spot (support)
    - d1_max/d1_min : bornes de move attendu (straddle ATM)

    Contrairement au classement GEX1-5 (non directionnel), ces niveaux ne sont
    cherchés que du côté où ils font sens comme support/résistance.

    Par défaut sur l'échéance la plus proche ; `all_expiries=True` agrège tout
    le df fourni (périmètre fixé en amont par `compute_levels`).
    """
    out: dict[str, float | None] = {
        "call_wall": None, "put_support": None, "d1_min": None, "d1_max": None,
    }
    if df.empty:
        return out
    nearest = df["expiry"].min()
    sub = df if all_expiries else df[df["expiry"] == nearest]
    # Le CLASSEMENT des murs se fait au spot de référence (structure figée) ;
    # le côté où on les cherche dépend en revanche du spot COURANT, une
    # résistance n'ayant de sens qu'au-dessus du marché du moment.
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
    """POINT D'ENTRÉE UNIQUE des niveaux affichés (murs GEX1-5 + call/put wall).

    Dashboard, API et bot l'appellent tous, pour ne PLUS JAMAIS diverger sur le
    spot de référence ou le périmètre d'échéances (le vrai bug identifié).

    - `structural_spot` : spot figé (clôture veille) → **magnitude** des murs
      (l'OI est une photo, on ne veut pas que le prix live déplace les murs) ;
    - `live_spot` : spot courant → **côté** (au-dessus/en dessous = résistance /
      support) ;
    - `bucket` : périmètre d'échéances (0DTE / Semaine / Mois / Tout), plus de
      filtre `expiry.min()` caché — les murs suivent ce qu'affiche l'interface.

    Renvoie {"levels": DataFrame GEX1-n, "keys": dict call_wall/put_support/1D}.
    """
    today = today or datetime.now(ET).date()
    sub = chain[bucket_mask(chain, bucket, today)] if not chain.empty else chain
    return {
        "levels": top_gex_levels(sub, n=n, ref_spot=structural_spot, all_expiries=True),
        "keys": key_levels(sub, live_spot, ref_spot=structural_spot, all_expiries=True),
    }
