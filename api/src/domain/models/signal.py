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

class SignalStatus(str, Enum):
    PROCESSING = "processing"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    REJECTED_UNSAFE = "rejected_unsafe"
    EXECUTING = "executing"
    FAILED = "failed"
    CANCELLED = "cancelled"

@dataclass
class Signal:
    id: Optional[str]
    userId: str
    source: str
    rawText: str
    status: SignalStatus
    createdAt: Any
    symbol: Optional[str] = None
    marketType: Optional[MarketType] = None
    decision: Optional[Decision] = None
    confidence: Optional[float] = None
    reasoning: Optional[str] = None
    riskScore: Optional[float] = None
    botId: Optional[str] = None
    tradeId: Optional[str] = None
    executionMessage: Optional[str] = None

    def to_dict(self):
        return {
            "id": self.id,
            "userId": self.userId,
            "source": self.source,
            "rawText": self.rawText,
            "status": self.status.value if hasattr(self.status, 'value') else str(self.status),
            "createdAt": self.createdAt.isoformat() if hasattr(self.createdAt, 'isoformat') else str(self.createdAt),
            "symbol": self.symbol,
            "marketType": self.marketType.value if hasattr(self.marketType, 'value') else (str(self.marketType) if self.marketType else None),
            "decision": self.decision.value if hasattr(self.decision, 'value') else (str(self.decision) if self.decision else None),
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "riskScore": self.riskScore,
            "botId": self.botId,
            "tradeId": self.tradeId,
            "executionMessage": self.executionMessage
        }
