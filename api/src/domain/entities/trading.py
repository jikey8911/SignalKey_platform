from dataclasses import dataclass
from typing import Optional, List
from datetime import datetime

@dataclass
class Ticker:
    symbol: str
    price: float
    timestamp: datetime

@dataclass
class Balance:
    asset: str
    free: float
    used: float
    total: float

@dataclass
class Order:
    id: str
    symbol: str
    type: str  # market, limit
    side: str  # buy, sell
    amount: float
    price: Optional[float]
    status: str
    timestamp: datetime
    filled: float
    remaining: float

@dataclass
class TradeResult:
    success: bool
    message: str
    order_id: Optional[str] = None
    price: Optional[float] = None
    amount: Optional[float] = None
    fee: Optional[float] = None
    timestamp: Optional[datetime] = None

@dataclass
class Position:
    symbol: str
    side: str  # LONG, SHORT
    amount: float
    entry_price: float
    unrealized_pnl: float = 0.0
    leverage: int = 1
    entries: List[float] = None # List of entry prices for accumulation tracking
    timestamp: datetime = datetime.now()
