"""Public API Facade for market-structure calculations.

This module acts as the central interface (facade) for the application layer.
All underlying mathematical functions, domain models, and business logic
have been refactored into `gex.calculations` and `gex.domain`.

Imports here exist solely to preserve the historical `gex.metrics` API
used by the dashboard (`app.py`), the API (`api.py`), and other integrations,
ensuring backward compatibility while maintaining clean internal boundaries.
"""
from .calculations import greeks
from .infrastructure import rates
from .config import CONTRACT_MULTIPLIER, SETTINGS
from .domain import DataQuality
from .domain.models import ChainSnapshot, SummaryMetrics
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
    summarize, regime_read, _evaluate_data_quality,
)
from .calculations.flow import put_call_ratios, oi_change, flow_delta

__all__ = [
    "ET", "YEAR_SECONDS", "EXPIRY_BUCKETS", "seconds_to_expiry", "enrich",
    "add_second_order", "bucket_mask", "exposure_by_strike",
    "gamma_profile", "gex_at_spot", "gex_by_strike_weighted", "net_gex_at",
    "zero_gamma", "third_friday", "front_futures_expiry", "futures_basis",
    "top_gex_levels", "expected_move", "key_levels", "compute_levels",
    "put_call_ratios", "SummaryMetrics", "summarize", "regime_read",
    "oi_change", "flow_delta", "ChainSnapshot",
]
