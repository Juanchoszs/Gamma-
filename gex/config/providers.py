"""Provider identity and capabilities.

Metadata only: no HTTP, authentication, or ingestion. Transport stays in
``gex.ingest``, ``gex.rtquote``, ``gex.futopt``, ``gex.idxopt``,
``gex.tt_auth``, and ``gex.backfill``.

Quality *thresholds* and ``DataQuality`` evaluation stay in ``gex.domain.quality``.
This module answers factual questions (who, delayed vs live, shareable?).
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ProviderType(str, Enum):
    CBOE = "cboe"
    DXFEED = "dxfeed"
    DATABENTO = "databento"


@dataclass(frozen=True)
class ProviderMetadata:
    """Capabilities of one canonical source identity."""

    identity: ProviderType
    # Domain quality bucket: cboe / dxfeed / native (see DataQualityConfig).
    quality_class: str
    delayed: bool
    live: bool
    historical: bool
    shareable: bool
    # Typical feed delay in seconds when delayed is True; 0 if live.
    expected_delay_seconds: int


# Canonical records. Aliases below map ingestion/export labels onto these keys.
PROVIDERS: dict[str, ProviderMetadata] = {
    "cboe": ProviderMetadata(
        identity=ProviderType.CBOE,
        quality_class="cboe",
        delayed=True,
        live=False,
        historical=False,
        shareable=True,
        expected_delay_seconds=900,
    ),
    "dxfeed": ProviderMetadata(
        identity=ProviderType.DXFEED,
        quality_class="dxfeed",
        delayed=False,
        live=True,
        historical=False,
        shareable=False,
        expected_delay_seconds=0,
    ),
    "dxfeed_public": ProviderMetadata(
        identity=ProviderType.DXFEED,
        quality_class="dxfeed",
        delayed=True,
        live=False,
        historical=False,
        shareable=False,
        expected_delay_seconds=1200,
    ),
    "native": ProviderMetadata(
        identity=ProviderType.DXFEED,
        quality_class="native",
        delayed=False,
        live=True,
        historical=False,
        shareable=False,
        expected_delay_seconds=0,
    ),
    "databento": ProviderMetadata(
        identity=ProviderType.DATABENTO,
        quality_class="cboe",
        delayed=False,
        live=False,
        historical=True,
        shareable=False,
        expected_delay_seconds=0,
    ),
}

# Ingestion and snapshot labels used around the codebase.
ALIASES: dict[str, str] = {
    "cboe": "cboe",
    "cboe_delayed": "cboe",
    "dxfeed": "dxfeed",
    "dxfeed_live": "dxfeed",
    "dxfeed_public": "dxfeed_public",
    "futopt": "native",
    "native": "native",
    "native_futures": "native",
    "native_index": "native",
    "databento": "databento",
}


def canonical_key(name: str) -> str | None:
    """Return a PROVIDERS key, or None if the label is unknown."""
    key = (name or "").lower().strip()
    if not key:
        return None
    if key in ALIASES:
        return ALIASES[key]
    return None


def resolve(name: str) -> ProviderMetadata | None:
    """Look up metadata for a source label. Unknown labels return None."""
    key = canonical_key(name)
    if key is None:
        return None
    return PROVIDERS[key]


def quality_class_for(name: str) -> str:
    """Quality bucket used by ``gex.domain.quality`` (not a quality verdict).

    Unknown names keep the historical fallback: substring hints, else CBOE.
    """
    meta = resolve(name)
    if meta is not None:
        return meta.quality_class
    normalized = (name or "").lower().strip()
    if "native" in normalized or "futopt" in normalized:
        return "native"
    if "dxfeed" in normalized:
        return "dxfeed"
    return "cboe"


def is_shareable(source: str) -> bool:
    """Export policy: only explicitly shareable provenance may leave the box.

    Unknown or missing labels are not shareable (exclude by default).
    """
    meta = resolve(source)
    return bool(meta and meta.shareable)
