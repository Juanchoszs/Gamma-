"""Automatic market report construction for GAMMA."""
from __future__ import annotations

from typing import Iterable

from gex.domain.market.intelligence import (
    LevelType,
    MarketLevel,
    MarketReport,
    MarketState,
    Scenario,
)
from gex.domain.market.scenarios import generate_level_scenarios


REPORT_LEVEL_TYPES = (
    LevelType.PUT_WALL,
    LevelType.CALL_WALL,
    LevelType.GEX_WALL,
    LevelType.GAMMA_FLIP,
    LevelType.HIGH_GAMMA,
    LevelType.LOW_GAMMA,
    LevelType.POC,
    LevelType.VAH,
    LevelType.VAL,
    LevelType.OVH,
    LevelType.OVL,
    LevelType.VOLUME_NODE,
    LevelType.OI_NODE,
)


def build_market_report(
    state: MarketState,
    levels: Iterable[MarketLevel],
    *,
    scenarios: Iterable[Scenario] | None = None,
    max_levels: int = 10,
    max_scenarios: int = 5,
) -> MarketReport:
    """Build the automatic market report from normalized analytical outputs."""
    if max_levels <= 0:
        key_levels: tuple[MarketLevel, ...] = ()
    else:
        key_levels = _rank_key_levels(tuple(levels), state, max_levels=max_levels)

    report_scenarios = tuple(scenarios) if scenarios is not None else generate_level_scenarios(
        state,
        key_levels,
        max_scenarios=max_scenarios,
    )

    return MarketReport(
        symbol=state.symbol,
        timestamp=state.timestamp,
        market_state=state,
        key_levels=key_levels,
        scenarios=report_scenarios[:max_scenarios],
        positioning_summary=_positioning_summary(key_levels),
        structure_summary=_structure_summary(state, key_levels, report_scenarios),
    )


def _rank_key_levels(
    levels: tuple[MarketLevel, ...],
    state: MarketState,
    *,
    max_levels: int,
) -> tuple[MarketLevel, ...]:
    required_levels = tuple(
        level for level in (
            state.nearest_support,
            state.nearest_resistance,
            state.major_gamma_level,
        )
        if level is not None
    )
    required_ids = {level.id for level in required_levels}
    levels_by_id = {
        level.id: level
        for level in levels
        if level.level_type in REPORT_LEVEL_TYPES or level.id in required_ids
    }
    for level in required_levels:
        levels_by_id[level.id] = level
    candidates = list(levels_by_id.values())
    ranked = sorted(
        candidates,
        key=lambda level: (
            level.id not in required_ids,
            abs(level.price - state.spot),
            -level.strength,
            level.price,
        ),
    )
    return tuple(ranked[:max_levels])


def _positioning_summary(levels: tuple[MarketLevel, ...]) -> tuple[str, ...]:
    summary: list[str] = []
    call_wall = _strongest_of_type(levels, LevelType.CALL_WALL)
    put_wall = _strongest_of_type(levels, LevelType.PUT_WALL)
    gamma_level = _strongest_gamma_level(levels)
    oi_level = _strongest_metric_level(levels, "open_interest")
    volume_level = _strongest_metric_level(levels, "volume")

    if call_wall is not None:
        summary.append(_level_metric_sentence("Call concentration", call_wall))
    if put_wall is not None:
        summary.append(_level_metric_sentence("Put concentration", put_wall))
    if gamma_level is not None:
        summary.append(_level_metric_sentence("Gamma concentration", gamma_level))
    if oi_level is not None:
        summary.append(
            f"Major OI reference is {oi_level.level_type.value} at {oi_level.price:g} "
            f"with open interest {_format_number(oi_level.open_interest)}."
        )
    if volume_level is not None:
        summary.append(
            f"Major volume reference is {volume_level.level_type.value} at {volume_level.price:g} "
            f"with volume {_format_number(volume_level.volume)}."
        )
    return tuple(summary)


def _structure_summary(
    state: MarketState,
    levels: tuple[MarketLevel, ...],
    scenarios: tuple[Scenario, ...],
) -> tuple[str, ...]:
    summary = [
        f"Spot {state.spot:g} is classified as {state.structure.value} in {state.session.value} session.",
        f"Gamma regime is {state.gamma_regime.value}; data status is {state.data_status}.",
    ]
    if state.nearest_support is not None:
        summary.append(
            f"Nearest support is {state.nearest_support.level_type.value} at {state.nearest_support.price:g} "
            f"({state.nearest_support.status.value})."
        )
    if state.nearest_resistance is not None:
        summary.append(
            f"Nearest resistance is {state.nearest_resistance.level_type.value} at {state.nearest_resistance.price:g} "
            f"({state.nearest_resistance.status.value})."
        )
    if state.major_gamma_level is not None:
        summary.append(
            f"Major gamma reference is {state.major_gamma_level.level_type.value} at "
            f"{state.major_gamma_level.price:g}."
        )
    interaction = _nearest_active_interaction(
        tuple(
            level for level in (
                state.major_gamma_level,
                state.nearest_support,
                state.nearest_resistance,
                *levels,
            )
            if level is not None
        )
    )
    if interaction is not None:
        summary.append(
            f"Price is {interaction.status.value} {interaction.level_type.value} at {interaction.price:g}."
        )
    if scenarios:
        summary.append(f"Active scenario: {scenarios[0].title}.")
    return tuple(summary)


def _strongest_of_type(levels: tuple[MarketLevel, ...], level_type: LevelType) -> MarketLevel | None:
    matches = [level for level in levels if level.level_type is level_type]
    if not matches:
        return None
    return max(matches, key=lambda level: (level.strength, level.volume or 0.0, level.open_interest or 0.0))


def _strongest_gamma_level(levels: tuple[MarketLevel, ...]) -> MarketLevel | None:
    matches = [
        level for level in levels
        if level.level_type in {
            LevelType.GEX_WALL,
            LevelType.GAMMA_FLIP,
            LevelType.HIGH_GAMMA,
            LevelType.LOW_GAMMA,
        }
    ]
    if not matches:
        return None
    return max(matches, key=lambda level: (level.strength, abs(level.gamma or 0.0)))


def _strongest_metric_level(levels: tuple[MarketLevel, ...], metric: str) -> MarketLevel | None:
    matches = [level for level in levels if getattr(level, metric) is not None]
    if not matches:
        return None
    return max(matches, key=lambda level: (getattr(level, metric) or 0.0, level.strength))


def _nearest_active_interaction(levels: tuple[MarketLevel, ...]) -> MarketLevel | None:
    actionable = [
        level for level in levels
        if level.status.value in {"APPROACHING", "TESTING", "RECLAIMED", "BROKEN"}
    ]
    if not actionable:
        return None
    gamma_types = {
        LevelType.GEX_WALL,
        LevelType.GAMMA_FLIP,
        LevelType.HIGH_GAMMA,
        LevelType.LOW_GAMMA,
    }
    return min(
        actionable,
        key=lambda level: (
            level.level_type not in gamma_types,
            abs(level.distance_percent or 0.0),
            -level.strength,
        ),
    )


def _level_metric_sentence(label: str, level: MarketLevel) -> str:
    return (
        f"{label}: {level.level_type.value} at {level.price:g} "
        f"with strength {level.strength}/100."
    )


def _format_number(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value:,.0f}"
