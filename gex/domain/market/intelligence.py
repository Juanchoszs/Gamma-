"""Domain contracts for GAMMA market intelligence.

These models describe normalized analytical outputs: levels, market state,
conditional scenarios and reports. They intentionally do not calculate GEX or
invent probabilities; engines can populate them from existing metrics.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Mapping


class LevelType(StrEnum):
    PUT_WALL = "PUT_WALL"
    CALL_WALL = "CALL_WALL"
    GEX_WALL = "GEX_WALL"
    HIGH_GAMMA = "HIGH_GAMMA"
    LOW_GAMMA = "LOW_GAMMA"
    POC = "POC"
    VAL = "VAL"
    VAH = "VAH"
    OVL = "OVL"
    OVH = "OVH"
    VOLUME_NODE = "VOLUME_NODE"
    OI_NODE = "OI_NODE"
    KEY_STRIKE = "KEY_STRIKE"
    GAMMA_FLIP = "GAMMA_FLIP"


class LevelSource(StrEnum):
    OPTIONS_CHAIN = "OPTIONS_CHAIN"
    OPTIONS_FLOW = "OPTIONS_FLOW"
    SESSION_PROFILE = "SESSION_PROFILE"
    PRICE_STRUCTURE = "PRICE_STRUCTURE"
    GEX_ENGINE = "GEX_ENGINE"


class LevelStatus(StrEnum):
    ACTIVE = "ACTIVE"
    APPROACHING = "APPROACHING"
    TESTING = "TESTING"
    ABOVE_LEVEL = "ABOVE_LEVEL"
    BELOW_LEVEL = "BELOW_LEVEL"
    RECLAIMED = "RECLAIMED"
    BROKEN = "BROKEN"
    STALE = "STALE"
    UNKNOWN = "UNKNOWN"


class SessionType(StrEnum):
    OVERNIGHT = "OVERNIGHT"
    REGULAR = "REGULAR"
    CLOSED = "CLOSED"
    UNKNOWN = "UNKNOWN"


class GammaRegime(StrEnum):
    POSITIVE_GAMMA = "POSITIVE_GAMMA"
    NEGATIVE_GAMMA = "NEGATIVE_GAMMA"
    NEUTRAL_GAMMA = "NEUTRAL_GAMMA"
    UNKNOWN = "UNKNOWN"


class MarketStructure(StrEnum):
    RANGE = "RANGE"
    EXPANSION = "EXPANSION"
    COMPRESSION = "COMPRESSION"
    TRANSITION = "TRANSITION"
    ABOVE_MAJOR_GAMMA = "ABOVE_MAJOR_GAMMA"
    BELOW_MAJOR_GAMMA = "BELOW_MAJOR_GAMMA"
    AT_MAJOR_GAMMA = "AT_MAJOR_GAMMA"
    UNKNOWN = "UNKNOWN"


class ScenarioDirection(StrEnum):
    UPSIDE = "UPSIDE"
    DOWNSIDE = "DOWNSIDE"
    RANGE = "RANGE"
    TRANSITION = "TRANSITION"


@dataclass(frozen=True)
class MarketLevel:
    id: str
    level_type: LevelType
    price: float
    source: LevelSource
    timestamp: datetime
    strength: int
    distance_percent: float | None = None
    expiration: datetime | None = None
    volume: float | None = None
    open_interest: float | None = None
    gamma: float | None = None
    delta: float | None = None
    vanna: float | None = None
    charm: float | None = None
    session: SessionType = SessionType.UNKNOWN
    status: LevelStatus = LevelStatus.UNKNOWN
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not 0 <= int(self.strength) <= 100:
            raise ValueError("strength must be a deterministic score from 0 to 100")
        if self.price <= 0:
            raise ValueError("level price must be positive")


@dataclass(frozen=True)
class MarketState:
    symbol: str
    timestamp: datetime
    spot: float
    gamma_regime: GammaRegime
    structure: MarketStructure
    session: SessionType
    nearest_support: MarketLevel | None = None
    nearest_resistance: MarketLevel | None = None
    major_gamma_level: MarketLevel | None = None
    data_status: str = "UNKNOWN"
    reasons: tuple[str, ...] = ()
    previous_spot: float | None = None
    implied_volatility: float | None = None
    positioning: str = "UNKNOWN"
    evaluated_levels: tuple[MarketLevel, ...] = ()

    @property
    def price_change(self) -> float | None:
        if self.previous_spot is None:
            return None
        return self.spot - self.previous_spot

    @property
    def price_change_percent(self) -> float | None:
        if self.previous_spot is None or self.previous_spot == 0:
            return None
        return (self.spot - self.previous_spot) / self.previous_spot * 100.0


@dataclass(frozen=True)
class Scenario:
    id: str
    title: str
    direction: ScenarioDirection
    trigger: str
    key_level: MarketLevel | None
    conditions: tuple[str, ...]
    structural_implication: str
    invalidation: str
    next_levels: tuple[MarketLevel, ...] = ()
    supporting_data: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class MarketReport:
    symbol: str
    timestamp: datetime
    market_state: MarketState
    key_levels: tuple[MarketLevel, ...]
    scenarios: tuple[Scenario, ...]
    positioning_summary: tuple[str, ...] = ()
    structure_summary: tuple[str, ...] = ()
