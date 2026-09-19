"""Deterministic, opt-in alert events for market-intelligence snapshots."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from gex.application.market_intelligence.service import MarketIntelligenceSnapshot
from gex.domain.market.intelligence import GammaRegime, LevelStatus, MarketLevel


class AlertKind(StrEnum):
    PRICE_REACHED_LEVEL = "PRICE_REACHED_LEVEL"
    LEVEL_BROKEN = "LEVEL_BROKEN"
    LEVEL_RECLAIMED = "LEVEL_RECLAIMED"
    LEVEL_STRENGTH_CHANGED = "LEVEL_STRENGTH_CHANGED"
    GAMMA_REGIME_CHANGED = "GAMMA_REGIME_CHANGED"


@dataclass(frozen=True)
class MarketAlert:
    kind: AlertKind
    symbol: str
    timestamp: str
    message: str
    level_id: str | None = None
    level_price: float | None = None
    previous_value: str | float | int | None = None
    current_value: str | float | int | None = None

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "kind": self.kind.value, "symbol": self.symbol,
            "timestamp": self.timestamp, "message": self.message,
        }
        for key, value in {
            "level_id": self.level_id, "level_price": self.level_price,
            "previous_value": self.previous_value, "current_value": self.current_value,
        }.items():
            if value is not None:
                payload[key] = value
        return payload


@dataclass(frozen=True)
class AlertConfig:
    strength_change_threshold: int = 15

    def __post_init__(self) -> None:
        if self.strength_change_threshold < 1:
            raise ValueError("strength_change_threshold must be positive")


def evaluate_alerts(
    previous: MarketIntelligenceSnapshot | None,
    current: MarketIntelligenceSnapshot,
    *,
    config: AlertConfig | None = None,
) -> tuple[MarketAlert, ...]:
    """Compare snapshots; the function deliberately has no delivery side effect."""
    if previous is None or previous.state.symbol != current.state.symbol:
        return ()
    cfg = config or AlertConfig()
    output: list[MarketAlert] = []
    if _regime_changed(previous.state.gamma_regime, current.state.gamma_regime):
        output.append(MarketAlert(
            kind=AlertKind.GAMMA_REGIME_CHANGED, symbol=current.state.symbol,
            timestamp=current.state.timestamp.isoformat(),
            message=f"Gamma regime changed from {previous.state.gamma_regime.value} to {current.state.gamma_regime.value}.",
            previous_value=previous.state.gamma_regime.value, current_value=current.state.gamma_regime.value,
        ))
    prior_levels = {level.id: level for level in previous.report.key_levels}
    for level in current.report.key_levels:
        prior = prior_levels.get(level.id)
        if prior is not None:
            output.extend(_level_alerts(prior, level, current, cfg))
    return tuple(output)


class AlertMonitor:
    """Small in-process monitor that is quiet until explicitly queried."""

    def __init__(self, config: AlertConfig | None = None) -> None:
        self._config = config or AlertConfig()
        self._snapshots: dict[str, MarketIntelligenceSnapshot] = {}

    def observe(self, snapshot: MarketIntelligenceSnapshot) -> tuple[MarketAlert, ...]:
        previous = self._snapshots.get(snapshot.state.symbol)
        alerts = evaluate_alerts(previous, snapshot, config=self._config)
        self._snapshots[snapshot.state.symbol] = snapshot
        return alerts

    def reset(self, symbol: str | None = None) -> None:
        """Forget prior observations when a user disables or retunes alerts."""
        if symbol is None:
            self._snapshots.clear()
        else:
            self._snapshots.pop(symbol.upper(), None)


def _regime_changed(previous: GammaRegime, current: GammaRegime) -> bool:
    return previous is not current and GammaRegime.UNKNOWN not in (previous, current)


def _level_alerts(previous: MarketLevel, current: MarketLevel,
                  snapshot: MarketIntelligenceSnapshot, config: AlertConfig) -> tuple[MarketAlert, ...]:
    common = {
        "symbol": snapshot.state.symbol, "timestamp": snapshot.state.timestamp.isoformat(),
        "level_id": current.id, "level_price": current.price,
    }
    alerts: list[MarketAlert] = []
    for status, kind, label in (
        (LevelStatus.TESTING, AlertKind.PRICE_REACHED_LEVEL, "Price reached"),
        (LevelStatus.BROKEN, AlertKind.LEVEL_BROKEN, "Level broken"),
        (LevelStatus.RECLAIMED, AlertKind.LEVEL_RECLAIMED, "Level reclaimed"),
    ):
        if current.status is status and previous.status is not status:
            alerts.append(MarketAlert(
                kind=kind, message=f"{label}: {current.level_type.value} at {current.price:g}.",
                previous_value=previous.status.value, current_value=current.status.value, **common,
            ))
    if abs(current.strength - previous.strength) >= config.strength_change_threshold:
        alerts.append(MarketAlert(
            kind=AlertKind.LEVEL_STRENGTH_CHANGED,
            message=f"Level strength changed for {current.level_type.value} at {current.price:g}.",
            previous_value=previous.strength, current_value=current.strength, **common,
        ))
    return tuple(alerts)
