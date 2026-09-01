from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from . import greeks
from ..infrastructure import rates
from ..config import CONTRACT_MULTIPLIER, SETTINGS
from ..domain import DataQuality
from ..domain.models import ChainSnapshot, SummaryMetrics

ET = ZoneInfo("America/New_York")
YEAR_SECONDS = 365.0 * 24 * 3600
EXPIRY_BUCKETS = ["0DTE", "Semaine", "Mois", "Tout"]
from .gex import bucket_mask
from .levels import futures_basis
from .gamma_flip import zero_gamma
from .flow import put_call_ratios


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
        source="cboe",  # CBOE is the default source for regime calculations
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
    """Cross reading Gamma/Delta: dealer hedging mechanics.

    - GEX: positive = dealers hedge against trend (dampening);
      negative = dealers hedge with trend (accelerating).
    - DEX: positive = dealers are long delta -> latent selling pressure (downward bias).
      Negative = short delta -> latent buying pressure (upward bias).
    """
    gex_frein = net_gex >= 0
    dex_long = net_dex >= 0   # dealers structurally long delta
    sens_delta = "long" if dex_long else "short"
    # language-agnostic codes (see gex/i18n.py)
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

