"""Puertos de salida para señales de trading."""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import List

from gex.analytics.domain.models import TradingSignal, SignalType

class SignalPort(ABC):
    @abstractmethod
    async def emit_signal(self, signal: TradingSignal) -> None:
        pass
    
    @abstractmethod
    async def get_active_signals(self, symbol: str) -> List[TradingSignal]:
        pass