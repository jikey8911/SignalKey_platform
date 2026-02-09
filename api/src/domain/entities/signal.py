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
    APPROVED = "approved"
    REJECTED = "rejected"
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"

class Direction(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"
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
    qty: Optional[float] = None
    status: str = "pending" # pending, hit

    def to_dict(self):
        return {
            "price": self.price,
            "percent": self.percent
        }

@dataclass
class TradingParameters:
    entry_price: Optional[float] = None
    entry_type: str = "market"  # "market" or "limit"
    tp: List[TakeProfit] = field(default_factory=list)
    sl: Optional[float] = None
    leverage: int = 1
    amount: Optional[float] = None
    investment: Optional[float] = None # Recommended investment value
    network: Optional[str] = None

    def to_dict(self):
        return {
            "entry_price": self.entry_price,
            "entry_type": self.entry_type,
            "tp": [tp.to_dict() if hasattr(tp, 'to_dict') else tp for tp in self.tp],
            "sl": self.sl,
            "leverage": self.leverage,
            "amount": self.amount,
            "network": self.network
        }

@dataclass
class SignalAnalysis:
    decision: Decision
    direction: Direction
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
    botId: Optional[str] = None
    tradeId: Optional[str] = None
    executionMessage: Optional[str] = None
    parameters: Optional[TradingParameters] = None

    def to_dict(self):
        return {
            "id": self.id,
            "userId": self.userId,
            "source": self.source,
            "rawText": self.rawText,
            "status": self.status.value if hasattr(self.status, 'value') else str(self.status),
            "createdAt": self.createdAt.isoformat() + ("Z" if not self.createdAt.tzinfo else "") if hasattr(self.createdAt, 'isoformat') else str(self.createdAt),
            "symbol": self.symbol,
            "marketType": self.marketType.value if hasattr(self.marketType, 'value') else (str(self.marketType) if self.marketType else None),
            "decision": self.decision.value if hasattr(self.decision, 'value') else (str(self.decision) if self.decision else None),
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "riskScore": self.riskScore,
            "botId": self.botId,
            "tradeId": self.tradeId,
            "executionMessage": self.executionMessage,
            "parameters": self.parameters.to_dict() if self.parameters and hasattr(self.parameters, 'to_dict') else (self.parameters if self.parameters else None)
        }
