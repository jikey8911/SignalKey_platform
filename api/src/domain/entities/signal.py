from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from enum import Enum
from datetime import datetime

class MarketType(str, Enum):
    CEX = "CEX"
    DEX = "DEX"
    SPOT = "SPOT"
    FUTURES = "FUTURES"

class Decision(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"

class SignalStatus(str, Enum):
    PROCESSING = "processing"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    REJECTED_UNSAFE = "rejected_unsafe"
    EXECUTING = "executing"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    FAILED = "failed"

@dataclass
class TakeProfit:
    price: float
    percent: float

@dataclass
class TradingParameters:
    entry_price: Optional[float] = None
    entry_type: str = "market"  # "market" or "limit"
    tp: List[TakeProfit] = field(default_factory=list)
    sl: Optional[float] = None
    leverage: int = 1
    amount: Optional[float] = None
    network: Optional[str] = None

@dataclass
class SignalAnalysis:
    decision: Decision
    symbol: str
    market_type: MarketType
    confidence: float
    reasoning: str
    is_safe: bool = True
    risk_score: float = 0.0
    parameters: TradingParameters = field(default_factory=TradingParameters)

@dataclass
class Signal:
    id: Optional[str]
    userId: str
    source: str
    rawText: str
    status: SignalStatus
    createdAt: datetime
    symbol: Optional[str] = None
    marketType: Optional[MarketType] = None
    decision: Optional[Decision] = None
    confidence: Optional[float] = None
    reasoning: Optional[str] = None
    riskScore: Optional[float] = None
    tradeId: Optional[str] = None
    executionMessage: Optional[str] = None
