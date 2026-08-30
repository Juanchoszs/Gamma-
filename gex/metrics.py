"""Public facade for market-structure calculations.

Implementations live in :mod:`gex.calculations`; imports here preserve the
historical ``gex.metrics`` API used by the dashboard and integrations.
"""
from . import greeks, rates
from .config import CONTRACT_MULTIPLIER, SETTINGS
from .domain import DataQuality
from .ingest import ChainSnapshot
from .calculations.gex import (
    ET, YEAR_SECONDS, EXPIRY_BUCKETS, seconds_to_expiry, enrich,
    add_second_order, bucket_mask, exposure_by_strike, gex_by_strike_weighted,
)
from .calculations.gamma_flip import gamma_profile, gex_at_spot, net_gex_at, zero_gamma
from .calculations.levels import (
    third_friday, front_futures_expiry, futures_basis, top_gex_levels,
    expected_move, key_levels, compute_levels,
)
from .calculations.regime import (
    SummaryMetrics, summarize, regime_read, _evaluate_data_quality,
)
from .calculations.flow import put_call_ratios, oi_change, flow_delta

__all__ = [
    "ET", "YEAR_SECONDS", "EXPIRY_BUCKETS", "seconds_to_expiry", "enrich",
    "add_second_order", "bucket_mask", "exposure_by_strike",
    "gamma_profile", "gex_at_spot", "gex_by_strike_weighted", "net_gex_at",
    "zero_gamma", "third_friday", "front_futures_expiry", "futures_basis",
    "top_gex_levels", "expected_move", "key_levels", "compute_levels",
    "put_call_ratios", "SummaryMetrics", "summarize", "regime_read",
    "oi_change", "flow_delta",
]
