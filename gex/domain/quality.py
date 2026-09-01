"""Data quality models for market data and snapshots."""
from __future__ import annotations

from enum import Enum
from dataclasses import dataclass, field
from typing import Optional


class DataQuality(Enum):
    """Data quality states for market data and snapshots.

    VALID       - Fresh, complete, structurally valid data
    WARNING     - Usable but with limitations (delayed feed, partial chain)
    STALE       - No recent update; latest known snapshot used but age is significant
    EXPIRED     - Contract/expiration no longer valid for active analysis
    INVALID     - Required data missing or structurally invalid
    MISSING     - No measurement exists (distinct from zero)
    """
    VALID = "VALID"
    WARNING = "WARNING"
    STALE = "STALE"
    EXPIRED = "EXPIRED"
    INVALID = "INVALID"
    MISSING = "MISSING"


@dataclass(frozen=True)
class ProviderQualityConfig:
    """Age thresholds for one provider class."""

    valid_seconds: int
    warning_seconds: int
    stale_seconds: int
    expired_seconds: int


@dataclass
class DataQualityConfig:
    """Centralized age thresholds grouped by provider class."""

    cboe: ProviderQualityConfig = field(
        default_factory=lambda: ProviderQualityConfig(30, 120, 300, 900)
    )
    dxfeed: ProviderQualityConfig = field(
        default_factory=lambda: ProviderQualityConfig(5, 30, 60, 300)
    )
    native: ProviderQualityConfig = field(
        default_factory=lambda: ProviderQualityConfig(10, 60, 180, 600)
    )


DEFAULT_QUALITY_CONFIG = DataQualityConfig()


def get_quality_config(
    provider: str, config: Optional[DataQualityConfig] = None
) -> ProviderQualityConfig:
    """Return the thresholds for a provider identifier."""
    from gex.config.providers import quality_class_for

    settings = config or DEFAULT_QUALITY_CONFIG
    return getattr(settings, quality_class_for(provider))


def evaluate_data_quality(
    age_seconds: Optional[float],
    provider: str,
    feed_timestamp: Optional[datetime] = None,
    has_required_fields: bool = True,
    is_expired_contract: bool = False,
    config: Optional[DataQualityConfig] = None,
) -> DataQuality:
    """Evaluate data quality based on age, provider, and completeness.

    Args:
        age_seconds: Seconds since data was fetched
        provider: Data source identifier (cboe, dxfeed, native, etc.)
        feed_timestamp: Original provider timestamp (unused but kept for compatibility)
        has_required_fields: Whether all required fields are present
        is_expired_contract: Whether the contract has expired
        config: Optional custom quality configuration

    Returns:
        DataQuality enum value
    """
    if is_expired_contract:
        return DataQuality.EXPIRED

    if age_seconds is None:
        return DataQuality.INVALID

    if not has_required_fields:
        return DataQuality.INVALID

    thresholds = get_quality_config(provider, config)
    if age_seconds <= thresholds.valid_seconds:
        return DataQuality.VALID
    elif age_seconds <= thresholds.warning_seconds:
        return DataQuality.WARNING
    elif age_seconds <= thresholds.stale_seconds:
        return DataQuality.STALE
    else:
        return DataQuality.EXPIRED