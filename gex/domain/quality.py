"""Data quality models for market data and snapshots."""
from __future__ import annotations

from enum import Enum
from dataclasses import dataclass
from datetime import datetime, timezone
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


@dataclass
class DataQualityConfig:
    """Centralized thresholds for data quality evaluation."""
    # Seconds thresholds for CBOE delayed data
    cboe_valid_seconds: int = 30
    cboe_warning_seconds: int = 120
    cboe_stale_seconds: int = 300
    cboe_expired_seconds: int = 900

    # Seconds thresholds for dxFeed realtime data
    dxfeed_valid_seconds: int = 5
    dxfeed_warning_seconds: int = 30
    dxfeed_stale_seconds: int = 60
    dxfeed_expired_seconds: int = 300

    # Seconds thresholds for native futures/options
    native_valid_seconds: int = 10
    native_warning_seconds: int = 60
    native_stale_seconds: int = 180
    native_expired_seconds: int = 600


DEFAULT_QUALITY_CONFIG = DataQualityConfig()


class DataQualityEvaluator:
    """Centralized data quality evaluation.

    Single authoritative location for assessing data quality from
    provider timestamps, snapshot age, and data completeness.
    """

    def __init__(self, config: Optional[DataQualityConfig] = None):
        self.config = config or DEFAULT_QUALITY_CONFIG

    def evaluate(
        self,
        age_seconds: Optional[float],
        provider: str,
        feed_timestamp: Optional[datetime] = None,
        has_required_fields: bool = True,
        is_expired_contract: bool = False,
    ) -> DataQuality:
        """Evaluate data quality based on age, provider, and completeness.

        Args:
            age_seconds: Seconds since data was fetched
            provider: Data source identifier (cboe, dxfeed, native, etc.)
            feed_timestamp: Original provider timestamp
            has_required_fields: Whether all required fields are present
            is_expired_contract: Whether the contract has expired

        Returns:
            DataQuality enum value
        """
        if is_expired_contract:
            return DataQuality.EXPIRED

        if age_seconds is None:
            return DataQuality.INVALID

        if not has_required_fields:
            return DataQuality.INVALID

        thresholds = self._get_thresholds(provider)
        if age_seconds <= thresholds.valid_seconds:
            return DataQuality.VALID
        elif age_seconds <= thresholds.warning_seconds:
            return DataQuality.WARNING
        elif age_seconds <= thresholds.stale_seconds:
            return DataQuality.STALE
        else:
            return DataQuality.EXPIRED

    def _get_thresholds(self, provider: str):
        """Get quality thresholds for a provider."""
        provider_lower = provider.lower()
        if "dxfeed" in provider_lower:
            return self.config.__dict__  # would need proper mapping
        elif "native" in provider_lower:
            return self.config.__dict__  # would need proper mapping
        else:
            return self.config.__dict__  # default CBOE


def evaluate_data_quality(
    age_seconds: Optional[float],
    feed_timestamp: Optional[datetime],
    provider: str,
    has_required_fields: bool = True,
    is_expired_contract: bool = False,
    config: Optional[DataQualityConfig] = None,
) -> DataQuality:
    """Module-level convenience function for backward compatibility."""
    evaluator = DataQualityEvaluator(config)
    return evaluator.evaluate(
        age_seconds=age_seconds,
        provider=provider,
        feed_timestamp=feed_timestamp,
        has_required_fields=has_required_fields,
        is_expired_contract=is_expired_contract,
    )