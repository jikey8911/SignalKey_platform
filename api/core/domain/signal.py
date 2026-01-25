from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from enum import Enum

class MarketType(str, Enum):
    CEX = "CEX"
    DEX = "DEX"
    SPOT = "SPOT"
    FUTURES = "FUTURES"

class Decision(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"

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
class RawSignal:
    source: str
    text: str
    metadata: Dict[str, Any] = field(default_factory=dict)
