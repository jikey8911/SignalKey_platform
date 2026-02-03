from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from api.src.domain.entities.trading import Ticker, Balance, Order, TradeResult
from api.src.domain.entities.signal import SignalAnalysis

class IExchangePort(ABC):
    @abstractmethod
    async def get_current_price(self, symbol: str, user_id: str) -> float:
        """Get the current price of a symbol."""
        pass

    @abstractmethod
    async def fetch_balance(self, user_id: str, exchange_id: Optional[str] = None) -> List[Balance]:
        """Fetch balance from the exchange."""
        pass

    @abstractmethod
    async def execute_trade(self, analysis: SignalAnalysis, user_id: str) -> TradeResult:
        """Execute a trade based on analysis."""
        pass

    @abstractmethod
    async def fetch_open_orders(self, user_id: str, symbol: Optional[str] = None) -> List[Order]:
        """Fetch open orders."""
        pass

    @abstractmethod
    async def get_historical_data(self, symbol: str, timeframe: str, limit: int = 1500, use_random_date: bool = False, user_id: str = "default_user") -> Any:
        """Fetch historical data as DataFrame."""
        pass

    @abstractmethod
    async def get_public_historical_data(self, symbol: str, timeframe: str, limit: int = 1500, use_random_date: bool = False, exchange_id: str = "binance") -> Any:
        """Fetch historical data using public API (no credentials required)."""
        pass

# Alias for backward compatibility
ExchangePort = IExchangePort
