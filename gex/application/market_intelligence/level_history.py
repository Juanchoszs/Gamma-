"""Serialize historical unified levels without inventing level trajectories."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

from gex.domain.market.intelligence import MarketLevel


@dataclass(frozen=True)
class LevelHistoryObservation:
    timestamp: datetime
    spot: float
    levels: tuple[MarketLevel, ...]


def build_level_history_payload(
    *,
    symbol: str,
    observations: Iterable[LevelHistoryObservation],
) -> dict:
    """Build chart-ready time series from previously observed levels.

    Multiple levels of a type are ranked per observation by existing strength,
    preserving what was observed rather than linking unrelated strikes by price.
    """
    ordered = sorted(observations, key=lambda observation: observation.timestamp)
    series: dict[str, dict] = {}
    spots: list[dict] = []
    for observation in ordered:
        spots.append({"timestamp": observation.timestamp.isoformat(), "price": observation.spot})
        by_type: dict[str, list[MarketLevel]] = {}
        for level in observation.levels:
            by_type.setdefault(level.level_type.value, []).append(level)
        for type_name, levels in by_type.items():
            ranked = sorted(levels, key=lambda level: (-level.strength, -abs(level.gamma or 0.0), level.price))
            for index, level in enumerate(ranked, start=1):
                series_id = f"{type_name}_{index}"
                entry = series.setdefault(series_id, {"id": series_id, "type": type_name, "points": []})
                entry["points"].append({
                    "timestamp": observation.timestamp.isoformat(),
                    "price": level.price,
                    "strength": level.strength,
                    "status": level.status.value,
                    "open_interest": level.open_interest,
                    "volume": level.volume,
                    "gamma": level.gamma,
                })
    return {
        "symbol": symbol,
        "observations": len(ordered),
        "spot": spots,
        "series": list(series.values()),
    }
