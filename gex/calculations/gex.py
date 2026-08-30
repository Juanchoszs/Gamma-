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
def seconds_to_expiry(expiries: pd.Series, now_et: datetime) -> np.ndarray:
    """Secondes jusqu'à l'expiration, échéance posée à 16:00 ET.

    Négatif = contrat expiré (0DTE après la cloche) — à exclure.
    """
    expiry_dt = pd.to_datetime(expiries).dt.tz_localize(ET) + pd.Timedelta(hours=16)
    return (expiry_dt - now_et).dt.total_seconds().to_numpy()


def enrich(snapshot: ChainSnapshot, now_et: datetime | None = None) -> pd.DataFrame:
    """Ajoute t, greeks calculés (BS sur l'IV du feed) et les colonnes GEX/DEX.

    Quand l'IV du feed est nulle/absente (deep ITM sans quote), on retombe
    sur les Greeks CBOE — leur gamma est ~0 sur ces contrats de toute façon.
    """
    now_et = now_et or datetime.now(ET)
    df = snapshot.options.copy()
    # exclut les contrats expirés (dont les 0DTE du jour après 16:00 ET,
    # dont les quotes résiduelles polluent GEX 0DTE et skew IV)
    secs = seconds_to_expiry(df["expiry"], now_et)
    df = df[secs > 0].reset_index(drop=True)
    s = snapshot.spot
    # plancher 5 min pour éviter les gammas explosifs à la cloche
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
    # Convention DIFFÉRENTE de celle du GEX, et c'est voulu. Le gamma d'une
    # option est TOUJOURS positif (call comme put) : sans un signe artificiel,
    # calls et puts seraient indiscernables — d'où le flip `sign` (dealers
    # longs calls / courts puts) qui fait tout le travail pour le GEX.
    # Le delta, lui, a DÉJÀ un signe naturel opposé entre call (positif) et
    # put (négatif) : réappliquer le MÊME flip différentiel par-dessus (essayé
    # le 2026-07-27, corrigé le 2026-07-28) rend CHAQUE contrat positif sans
    # exception — un call devient +δ_call, un put devient -1×δ_put = +|δ_put| :
    # les deux positifs, plus aucun strike ne peut jamais ressortir négatif.
    # Ce n'était pas visible sur les tests d'agrégat (qui ne regardent que le
    # NET), mais sautait aux yeux sur le graphique par strike — barres toutes
    # bleues, plus aucune rouge.
    #
    # La convention correcte pour le DEX (cf. MenthorQ, FlashAlpha) suppose
    # les dealers COURTS des deux côtés (calls ET puts — hypothèse que les
    # clients achètent des calls pour l'upside ET des puts en protection),
    # donc une négation UNIFORME du delta brut, pas un flip différentiel :
    # court un call -> -δ_call (négatif, cohérent) ; court un put ->
    # -δ_put = +|δ_put| (positif, cohérent) — les deux types redeviennent
    # discernables. Le NET reste cohérent avec le récit du GEX : plus de puts
    # -> dealers plus courts puts -> plus longs delta -> DEX net positif,
    # exactement comme avant, mais construit sans casser le signe par strike.
    df["dex"] = -1.0 * d * oi * CONTRACT_MULTIPLIER * s
    # Spot répété sur chaque ligne : un snapshot persisté devient ainsi
    # auto-suffisant, et le backtest peut en recalculer les niveaux sans aller
    # chercher le prix ailleurs. Une constante ne coûte rien en Parquet.
    df["spot"] = float(s)
    return df


def add_second_order(df: pd.DataFrame, spot: float) -> pd.DataFrame:
    """Ajoute vanna/charm et leurs expositions en $.

    Conventions (mêmes hypothèses de signe que le GEX : dealers longs calls,
    courts puts) :
    - vex   : $ de delta par POINT DE VOL (1 %) — l'ampleur du re-hedging
              quand l'IV bouge d'un point.
    - cex   : $ de delta par JOUR écoulé — le flux mécanique que les dealers
              doivent absorber par simple passage du temps.
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
        # échéance la plus proche : le vrai 0DTE en séance (elle == today),
        # la prochaine séance hors séance/week-end (cohérent avec top_gex_levels
        # et le bandeau de niveaux, qui utilisent aussi l'échéance min).
        if df.empty:
            return pd.Series(False, index=df.index)
        return df["expiry"] == df["expiry"].min()
    if bucket == "Semaine":
        return df["expiry"] <= today + timedelta(days=7)
    if bucket == "Mois":
        return df["expiry"] <= today + timedelta(days=35)
    return pd.Series(True, index=df.index)


def exposure_by_strike(df: pd.DataFrame, col: str) -> pd.DataFrame:
    """Agrège gex/dex par strike, calls et puts séparés + net."""
    pivot = df.pivot_table(index="strike", columns="type", values=col, aggfunc="sum").fillna(0.0)
    for side in ("C", "P"):
        if side not in pivot:
            pivot[side] = 0.0
    pivot["net"] = pivot["C"] + pivot["P"]
    return pivot.reset_index()


def gex_by_strike_weighted(df: pd.DataFrame, spot: float,
                           weight_col: str = "open_interest") -> pd.Series:
    """GEX par strike, pondéré par l'open interest ou par le volume du jour.

    Les deux racontent des choses différentes : l'open interest décrit le
    positionnement installé, le volume ce qui se traite aujourd'hui et donc se
    couvre maintenant. Superposés, l'écart entre les deux signale un strike qui
    prend de l'importance en séance sans figurer dans la structure de la veille.
    """
    if df.empty or weight_col not in df.columns:
        return pd.Series(dtype=float)
    sign = np.where((df["type"] == "C").to_numpy(), 1.0, -1.0)
    gex = (sign * df["gamma_bs"].to_numpy() * df[weight_col].to_numpy()
           * CONTRACT_MULTIPLIER * spot ** 2 * 0.01)
    return pd.Series(gex, index=df["strike"].to_numpy()).groupby(level=0).sum()

