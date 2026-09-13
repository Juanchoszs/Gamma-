"""Puertos de entrada para datos de mercado - Arquitectura Hexagonal."""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

@dataclass
class MarketDataRequest:
    symbol: str
    start_date: datetime
    end_date: datetime
    include_options: bool = True

@dataclass
class MarketData:
    symbol: str
    spot: float
    timestamp: datetime
    options_chain: Optional[List] = None

class MarketDataPort(ABC):
    @abstractmethod
    async def get_market_data(self, request: MarketDataRequest) -> MarketData:
        pass