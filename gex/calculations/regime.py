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
from .gex import bucket_mask
from .levels import futures_basis
from .gamma_flip import zero_gamma
from .flow import put_call_ratios

@dataclass
class SummaryMetrics:
    timestamp: datetime
    symbol: str
    spot: float
    net_gex: float
    zero_gamma: float | None
    pc_oi: float
    pc_volume: float
    net_gex_0dte: float = 0.0
    basis: float | None = None
    net_dex: float | None = None
    # Provenance of the row. Determines what can be shared: "cboe" =
    # free public source, redistributable; "databento" = paid source
    # under personal use license, NOT redistributable.
    source: str = "cboe"
    data_quality: DataQuality = DataQuality.VALID
    age_seconds: float | None = None

    def as_row(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "symbol": self.symbol,
            "spot": self.spot,
            "net_gex": self.net_gex,
            "zero_gamma": self.zero_gamma,
            "pc_oi": self.pc_oi,
            "pc_volume": self.pc_volume,
            "net_gex_0dte": self.net_gex_0dte,
            "basis": self.basis,
            "net_dex": self.net_dex,
            "source": self.source,
            "data_quality": self.data_quality.value,
            "age_seconds": self.age_seconds,
        }


def summarize(snapshot: ChainSnapshot, df: pd.DataFrame,
              with_basis: bool = True) -> SummaryMetrics:
    """with_basis=False for underlyings without associated future (ETF):
    call-put parity would measure a simple dividend carry, which would be
    misleading to store under the name 'basis'."""
    now_et = datetime.now(ET)
    today = now_et.date()
    ratios = put_call_ratios(df)

    # Compute data age - handle timezone mismatch
    age_seconds = None
    if snapshot.fetched_at is not None:
        # Ensure both datetimes are timezone-aware for subtraction
        fetched_at = snapshot.fetched_at
        if fetched_at.tzinfo is None:
            # Assume UTC if naive (as per ingest.py which uses datetime.utcnow())
            fetched_at = fetched_at.replace(tzinfo=timezone.utc)
        age_seconds = (now_et - fetched_at).total_seconds()

    # Determine data quality based on age and completeness
    data_quality = _evaluate_data_quality(
        age_seconds=age_seconds,
        feed_timestamp=snapshot.feed_timestamp,
        df=df,
        source=snapshot.symbol,
    )

    # Compute net_dex handling NaN values (missing DEX data)
    dex_series = df["dex"] if "dex" in df.columns else pd.Series(dtype=float)
    if dex_series.notna().any():
        net_dex = float(np.nansum(dex_series))
    else:
        net_dex = None

    return SummaryMetrics(
        timestamp=snapshot.feed_timestamp,
        symbol=snapshot.symbol,
        spot=snapshot.spot,
        net_gex=float(df["gex"].sum()),
        zero_gamma=zero_gamma(df, snapshot.spot),
        pc_oi=ratios["pc_oi"],
        pc_volume=ratios["pc_volume"],
        net_gex_0dte=float(df.loc[bucket_mask(df, "0DTE", today), "gex"].sum()),
        basis=futures_basis(df, snapshot.spot, today) if with_basis else None,
        net_dex=net_dex,
        data_quality=data_quality,
        age_seconds=age_seconds,
    )


def _evaluate_data_quality(
    age_seconds: float | None,
    feed_timestamp: datetime,
    df: pd.DataFrame,
    source: str,
) -> DataQuality:
    """Centralized data quality evaluation.

    Args:
        age_seconds: Seconds since data was fetched
        feed_timestamp: Timestamp from the data provider
        df: Enriched option chain DataFrame
        source: Data source identifier

    Returns:
        DataQuality enum value
    """
    if age_seconds is None:
        return DataQuality.INVALID

    if age_seconds <= 30:
        return DataQuality.VALID
    elif age_seconds <= 120:
        return DataQuality.WARNING
    elif age_seconds <= 300:
        return DataQuality.STALE
    else:
        return DataQuality.EXPIRED


def regime_read(net_gex: float, net_dex: float,
                 dex_history: pd.Series | None = None) -> dict:
    """Lecture croisée Gamma/Delta : mécanique de couverture des dealers, pas
    un signal d'entrée. Deux axes indépendants :

    - GEX (comment un mouvement se comporte une fois lancé) : positif = les
      dealers vendent les hausses et achètent les baisses, donc freinent ;
      négatif = l'inverse, donc amplifient.
    - DEX (le sens de l'obligation de couverture latente des dealers, sous
      l'hypothèse longs calls / courts puts, cf. `enrich`) : positif = ils
      sont structurellement LONGS delta (côté puts vendus qui s'enfoncent
      dans la monnaie) → pression de couverture VENDEUSE latente, biais
      baissier si un mouvement démarre. Négatif = l'inverse (short delta),
      pression ACHETEUSE latente, biais haussier.

    Ni l'un ni l'autre ne dit SI un mouvement démarre, ni dans quel sens il
    démarre — seulement sa nature probable s'il se produit. `dex_history`
    (série de |net_dex| passés du même sous-jacent) sert uniquement à situer
    l'ampleur actuelle par rang percentile ; sans historique suffisant (< 20
    points), la magnitude est laissée à None plutôt que devinée.
    """
    gex_frein = net_gex >= 0
    dex_long = net_dex >= 0   # dealers structurellement longs delta
    sens_delta = "long" if dex_long else "short"
    # codes neutres (pas de mot figé dans une langue) : gex/i18n.py les
    # traduit en "vendeuse"/"acheteuse" (fr) ou "selling"/"buying" (en)
    pression_code = "sell" if dex_long else "buy"
    biais_code = "down" if dex_long else "up"

    magnitude = None
    if dex_history is not None:
        ref = dex_history.dropna().abs()
        if len(ref) >= 20:
            rank = (ref < abs(net_dex)).mean()
            magnitude = "fort" if rank >= 0.67 else ("faible" if rank <= 0.33 else None)

    params = {"sens_delta": sens_delta, "pression_code": pression_code,
              "biais_code": biais_code}
    if gex_frein:
        key, severity = "regime_frein", "info"
    elif magnitude == "fort":
        key, severity = "regime_accel_fort", "danger"
    else:
        key, severity = "regime_accel_modere", "warning"

    return {
        "gex_frein": gex_frein,
        "dex_sign": sens_delta,
        "magnitude": magnitude,
        "severity": severity,
        "i18n_key": key,
        "params": params,
    }

