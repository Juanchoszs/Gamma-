"""Application orchestration for the GAMMA automatic market engine."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

from gex.domain.market.intelligence import (
    MarketLevel,
    MarketReport,
    MarketState,
    Scenario,
    SessionType,
)
from gex.domain.market.reports import build_market_report
from gex.domain.market.scenarios import generate_level_scenarios
from gex.domain.market.state import build_market_state


@dataclass(frozen=True)
class MarketIntelligenceConfig:
    """Deterministic settings for market-intelligence generation."""

    max_scenarios: int = 5
    max_report_levels: int = 16
    neutral_gex_threshold: float = 0.0

    def __post_init__(self) -> None:
        if self.max_scenarios < 0:
            raise ValueError("max_scenarios must be non-negative")
        if self.max_report_levels < 0:
            raise ValueError("max_report_levels must be non-negative")
        if self.neutral_gex_threshold < 0:
            raise ValueError("neutral_gex_threshold must be non-negative")


@dataclass(frozen=True)
class MarketIntelligenceSnapshot:
    """Complete backend output for market state, scenarios and report views."""

    state: MarketState
    scenarios: tuple[Scenario, ...]
    report: MarketReport
    levels: tuple[MarketLevel, ...] = ()


def build_market_intelligence_snapshot(
    *,
    symbol: str,
    spot: float,
    timestamp: datetime,
    levels: Iterable[MarketLevel],
    net_gex: float | None = None,
    session: SessionType = SessionType.UNKNOWN,
    previous_spot: float | None = None,
    data_status: str = "UNKNOWN",
    implied_volatility: float | None = None,
    call_open_interest: float | None = None,
    put_open_interest: float | None = None,
    config: MarketIntelligenceConfig | None = None,
) -> MarketIntelligenceSnapshot:
    """Build the automatic market-intelligence output from normalized inputs.

    The service composes existing domain engines. It does not fetch provider
    data, recalculate GEX, or invent probabilities.
    """
    cfg = config or MarketIntelligenceConfig()
    normalized_levels = tuple(levels)
    state = build_market_state(
        symbol=symbol,
        spot=spot,
        timestamp=timestamp,
        levels=normalized_levels,
        net_gex=net_gex,
        session=session,
        previous_spot=previous_spot,
        data_status=data_status,
        neutral_gex_threshold=cfg.neutral_gex_threshold,
        implied_volatility=implied_volatility,
        call_open_interest=call_open_interest,
        put_open_interest=put_open_interest,
    )
    evaluated_levels = state.evaluated_levels
    report_seed = build_market_report(
        state,
        evaluated_levels,
        max_levels=cfg.max_report_levels,
        max_scenarios=cfg.max_scenarios,
    )
    scenarios = generate_level_scenarios(
        state,
        report_seed.key_levels,
        max_scenarios=cfg.max_scenarios,
    )
    report = build_market_report(
        state,
        evaluated_levels,
        scenarios=scenarios,
        max_levels=cfg.max_report_levels,
        max_scenarios=cfg.max_scenarios,
    )
    return MarketIntelligenceSnapshot(
        state=state,
        scenarios=scenarios,
        report=report,
        levels=evaluated_levels,
    )
