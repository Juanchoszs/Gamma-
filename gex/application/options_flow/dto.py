"""View models for the options-flow overlay."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import pandas as pd

from gex.application.options_flow.service import FlowBubble


@dataclass(frozen=True)
class GEXLevel:
    name: str
    price: float
    value: float | None = None
    visible: bool = True
    style: str = "solid"
    side: str | None = None
    open_interest: float | None = None
    volume: float | None = None
    color_key: str | None = None
    glow_key: str | None = None


@dataclass(frozen=True)
class OptionsOverlayViewModel:
    symbol: str
    price_series: pd.DataFrame
    current_price: float | None
    chain: pd.DataFrame | None
    gamma_flip: float | None
    keys: dict
    day: str
    window: float
    previous_price_series: pd.DataFrame | None = None
    gex_levels: list[GEXLevel] = field(default_factory=list)
    flow_bubbles: list[FlowBubble] = field(default_factory=list)
    snapshots: list[tuple[datetime, pd.DataFrame]] = field(default_factory=list)
