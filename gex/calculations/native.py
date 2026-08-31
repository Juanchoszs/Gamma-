"""Transform native option chains into snapshot + summary metrics."""
from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
import pandas as pd

from ..domain import DataQuality
from ..ingest import ChainSnapshot
from .flow import put_call_ratios
from .gamma_flip import zero_gamma
from .gex import bucket_mask
from .regime import ET, SummaryMetrics


def build_native_summary(code: str, df: pd.DataFrame,
                          now_et: datetime | None = None) -> tuple[ChainSnapshot, SummaryMetrics]:
    """Build a summary for a native future-options chain."""
    now_et = now_et or datetime.now(ET)
    spot = float(df["spot"].iloc[0])
    ratios = put_call_ratios(df)
    today = now_et.date()
    snap = ChainSnapshot(
        symbol=code,
        spot=spot,
        feed_timestamp=now_et.replace(tzinfo=None),
        fetched_at=datetime.now(UTC),
        options=df,
    )
    age_seconds = (now_et - snap.fetched_at).total_seconds()

    dex_series = df["dex"] if "dex" in df.columns else pd.Series(dtype=float)
    if dex_series.notna().any():
        net_dex = float(np.nansum(dex_series))
    else:
        net_dex = None

    summary = SummaryMetrics(
        timestamp=snap.feed_timestamp,
        symbol=code,
        spot=spot,
        net_gex=float(df["gex"].sum()),
        zero_gamma=zero_gamma(df, spot),
        pc_oi=ratios["pc_oi"],
        pc_volume=ratios["pc_volume"],
        net_gex_0dte=float(df.loc[bucket_mask(df, "0DTE", today), "gex"].sum()),
        net_dex=net_dex,
        basis=None,
        source="dxfeed",
        data_quality=DataQuality.VALID,
        age_seconds=age_seconds,
    )
    return snap, summary
