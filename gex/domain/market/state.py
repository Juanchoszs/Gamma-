"""Deterministic market-state construction from normalized levels."""
from __future__ import annotations

from datetime import datetime
from typing import Iterable

from gex.domain.market.intelligence import (
    GammaRegime,
    LevelStatus,
    LevelType,
    MarketLevel,
    MarketState,
    MarketStructure,
    SessionType,
)
from gex.domain.market.interaction import update_level_interaction

GAMMA_LEVEL_TYPES = {
    LevelType.GEX_WALL,
    LevelType.GAMMA_FLIP,
    LevelType.HIGH_GAMMA,
    LevelType.LOW_GAMMA,
}


def classify_gamma_regime(net_gex: float | None, *, neutral_threshold: float = 0.0) -> GammaRegime:
    """Classify gamma regime from an existing net-GEX value."""
    if net_gex is None:
        return GammaRegime.UNKNOWN
    if neutral_threshold < 0:
        raise ValueError("neutral threshold must be non-negative")
    if net_gex > neutral_threshold:
        return GammaRegime.POSITIVE_GAMMA
    if net_gex < -neutral_threshold:
        return GammaRegime.NEGATIVE_GAMMA
    return GammaRegime.NEUTRAL_GAMMA


def build_market_state(
    *,
    symbol: str,
    spot: float,
    timestamp: datetime,
    levels: Iterable[MarketLevel],
    net_gex: float | None = None,
    session: SessionType = SessionType.UNKNOWN,
    previous_spot: float | None = None,
    data_status: str = "UNKNOWN",
    neutral_gex_threshold: float = 0.0,
    implied_volatility: float | None = None,
    call_open_interest: float | None = None,
    put_open_interest: float | None = None,
) -> MarketState:
    """Build current market state without recalculating underlying analytics."""
    if spot <= 0:
        raise ValueError("spot must be positive")
    updated_levels = tuple(
        update_level_interaction(level, spot, previous_spot=previous_spot)
        for level in levels
    )
    nearest_support = _nearest_below(updated_levels, spot)
    nearest_resistance = _nearest_above(updated_levels, spot)
    major_gamma_level = _major_gamma_level(updated_levels)
    gamma_regime = classify_gamma_regime(net_gex, neutral_threshold=neutral_gex_threshold)
    positioning = classify_positioning(call_open_interest, put_open_interest)
    structure = _market_structure(spot, major_gamma_level)
    reasons = _state_reasons(
        gamma_regime=gamma_regime,
        structure=structure,
        nearest_support=nearest_support,
        nearest_resistance=nearest_resistance,
        major_gamma_level=major_gamma_level,
        implied_volatility=implied_volatility,
        positioning=positioning,
    )
    return MarketState(
        symbol=symbol,
        timestamp=timestamp,
        spot=float(spot),
        gamma_regime=gamma_regime,
        structure=structure,
        session=session,
        nearest_support=nearest_support,
        nearest_resistance=nearest_resistance,
        major_gamma_level=major_gamma_level,
        data_status=data_status,
        reasons=reasons,
        previous_spot=float(previous_spot) if previous_spot is not None and previous_spot > 0 else None,
        implied_volatility=float(implied_volatility) if implied_volatility is not None and implied_volatility >= 0 else None,
        positioning=positioning,
        evaluated_levels=updated_levels,
    )


def classify_positioning(call_open_interest: float | None, put_open_interest: float | None) -> str:
    """Classify current OI balance without projecting a market outcome."""
    if call_open_interest is None or put_open_interest is None:
        return "UNKNOWN"
    if call_open_interest > put_open_interest:
        return "CALL_HEAVY"
    if put_open_interest > call_open_interest:
        return "PUT_HEAVY"
    return "BALANCED"


def _nearest_below(levels: tuple[MarketLevel, ...], spot: float) -> MarketLevel | None:
    candidates = [level for level in levels if level.price <= spot]
    if not candidates:
        return None
    return max(candidates, key=lambda level: (level.price, level.strength))


def _nearest_above(levels: tuple[MarketLevel, ...], spot: float) -> MarketLevel | None:
    candidates = [level for level in levels if level.price >= spot]
    if not candidates:
        return None
    return min(candidates, key=lambda level: (level.price, -level.strength))


def _major_gamma_level(levels: tuple[MarketLevel, ...]) -> MarketLevel | None:
    candidates = [level for level in levels if level.level_type in GAMMA_LEVEL_TYPES]
    if not candidates:
        return None
    return max(candidates, key=lambda level: (level.strength, abs(level.gamma or 0.0)))


def _market_structure(spot: float, major_gamma_level: MarketLevel | None) -> MarketStructure:
    if major_gamma_level is None:
        return MarketStructure.UNKNOWN
    if major_gamma_level.status is LevelStatus.TESTING:
        return MarketStructure.AT_MAJOR_GAMMA
    if spot > major_gamma_level.price:
        return MarketStructure.ABOVE_MAJOR_GAMMA
    if spot < major_gamma_level.price:
        return MarketStructure.BELOW_MAJOR_GAMMA
    return MarketStructure.AT_MAJOR_GAMMA


def _state_reasons(
    *,
    gamma_regime: GammaRegime,
    structure: MarketStructure,
    nearest_support: MarketLevel | None,
    nearest_resistance: MarketLevel | None,
    major_gamma_level: MarketLevel | None,
    implied_volatility: float | None,
    positioning: str,
) -> tuple[str, ...]:
    reasons = [f"Gamma regime classified as {gamma_regime.value} from net GEX input."]
    if major_gamma_level is not None:
        reasons.append(
            f"Major gamma level is {major_gamma_level.level_type.value} at {major_gamma_level.price:g}."
        )
        reasons.append(f"Spot structure is {structure.value} relative to major gamma.")
    if nearest_support is not None:
        reasons.append(f"Nearest support candidate is {nearest_support.level_type.value} at {nearest_support.price:g}.")
    if nearest_resistance is not None:
        reasons.append(
            f"Nearest resistance candidate is {nearest_resistance.level_type.value} at {nearest_resistance.price:g}."
        )
    if implied_volatility is not None:
        reasons.append(f"Median implied volatility is {implied_volatility:.1%}.")
    if positioning != "UNKNOWN":
        reasons.append(f"Open-interest positioning is {positioning}.")
    return tuple(reasons)
