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
def gamma_profile(df: pd.DataFrame, spot: float, weight_col: str = "open_interest",
                  range_pct: float | None = None, steps: int | None = None
                  ) -> tuple[np.ndarray, np.ndarray] | None:
    """Profil de GEX net recalculé sur une grille de spots hypothétiques.

    IV et maturités sont figées : on ne simule que le déplacement du spot, ce
    qui isole l'effet de position. La pente au niveau du spot dit à quelle
    vitesse le régime se dégrade ; les creux signalent les zones
    d'accélération.

    Retourne (grille de spots, GEX net en $ par 1 %), ou None si rien d'exploitable.
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
    """GEX par strike, gamma RECALCULÉ à un spot de référence donné.

    Distinct de `gex_by_strike_weighted`, qui réutilise le gamma déjà stocké —
    donc celui du spot au moment du pull.

    Pourquoi c'est nécessaire : le gamma culmine à la monnaie. Évalué au spot
    courant, le strike au plus fort |GEX| migre avec le prix, et le « mur »
    finit par désigner l'endroit où se trouve le marché plutôt qu'une zone de
    couverture. Mesuré sur une chaîne SPX réelle, faire varier la référence de
    7350 à 7500 déplace les cinq murs de bout en bout.

    Un mur est une propriété de la distribution d'open interest, qui ne change
    qu'une fois par jour. L'évaluer à un spot figé — la clôture de la veille,
    quand cet open interest a été arrêté — le rend stable en séance, ce qu'un
    plan de trading exige.
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
    """GEX net recalculé à un spot donné, IV et maturités figées.

    Sert à rafraîchir le GEX net au spot temps réel sans chaîne d'options
    fraîche : l'open interest ne change qu'une fois par jour et l'IV bouge
    lentement, alors que le gamma de chaque contrat suit le spot en continu.
    C'est donc le spot qui rend la mesure périmée, pas la chaîne.

    Le calcul est celui de `gamma_profile` évalué en un point, donc sur le même
    sous-ensemble de contrats que le Gamma Flip : GEX net et distance au flip
    restent cohérents entre eux, ce qui est ce qui compte pour lire le régime.
    """
    res = gamma_profile(df, spot, weight_col, range_pct=0.0, steps=1)
    return None if res is None else float(res[1][0])


def zero_gamma(df: pd.DataFrame, spot: float, weight_col: str = "open_interest") -> float | None:
    """Niveau de spot où le GEX net (recalculé à ce spot) change de signe.

    Recalcule le gamma BS sur une grille de spots ±zg_range en gardant IV et
    t figés, puis interpole le passage par zéro le plus proche du spot.

    weight_col="open_interest" : le flip structurel (zero gamma classique).
    weight_col="volume"        : le HVL façon volatility trigger — bascule du
    profil pondéré par ce qui se traite (et donc se hedge) aujourd'hui.
    """
    res = gamma_profile(df, spot, weight_col)
    if res is None:
        return None
    grid, profile = res
    crossings = np.where(np.diff(np.sign(profile)) != 0)[0]
    if len(crossings) == 0:
        return None
    # passage par zéro le plus proche du spot
    idx = crossings[np.argmin(np.abs(grid[crossings] - spot))]
    x0, x1 = grid[idx], grid[idx + 1]
    y0, y1 = profile[idx], profile[idx + 1]
    return float(x0 - y0 * (x1 - x0) / (y1 - y0))

