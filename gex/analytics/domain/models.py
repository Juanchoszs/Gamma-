"""Modelos de dominio para el motor analítico hexagonal.

Entidades core del dominio: GEX, DEX, Levels, Regime, etc.
"""
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional, List


class SignalType(Enum):
    CALL_SIGNAL = "call_signal"
    PUT_SIGNAL = "put_signal"
    REGIME_CHANGE = "regime_change"
    LEVEL_BREACH = "level_breach"


class RegimeType(Enum):
    STABILIZING = "stabilizing"
    ACCELERATING = "accelerating"
    NEUTRAL = "neutral"


@dataclass
class OptionContract:
    """Contrato de opciones como value object."""
    symbol: str
    strike: float
    expiry: datetime
    option_type: str  # "call" or "put"
    open_interest: float
    implied_volatility: float
    delta: float
    gamma: float


@dataclass
class GEXProfile:
    """Perfil de Gamma Exposure calculado."""
    symbol: str
    timestamp: datetime
    net_gex: float
    call_gex: float
    put_gex: float
    zero_gamma: float
    bucket: str
    unit: str  # "$Bn" or "$M"


@dataclass
class DEXProfile:
    """Perfil de Delta Exposure calculado."""
    symbol: str
    timestamp: datetime
    net_dex: float
    long_delta: float
    short_delta: float
    bucket: str


@dataclass
class RegimeState:
    """Estado de régimen de mercado."""
    symbol: str
    timestamp: datetime
    regime_type: RegimeType
    delta_dealers: str  # "long" or "short"
    coverage_pressure: str  # "high", "medium", "low"
    confidence: float  # 0.0 to 1.0


@dataclass
class KeyLevel:
    """Nivel clave identificado."""
    level_type: str  # "call_wall", "put_support", "gamma_flip", "hvl"
    price: float
    strength: float  # 0.0 to 1.0
    timestamp: datetime


@dataclass
class TradingSignal:
    """Señal de trading generada."""
    signal_type: SignalType
    symbol: str
    strength: float  # 0.0 to 1.0
    confidence: float  # 0.0 to 1.0
    timestamp: datetime
    metadata: dict
    reasoning: str