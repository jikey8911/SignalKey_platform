from pydantic import BaseModel
from typing import Optional, Dict, Any

class TradingSignal(BaseModel):
    source: str  # e.g., "telegram", "webhook"
    raw_text: str
    metadata: Optional[Dict[str, Any]] = None

class AnalysisResult(BaseModel):
    decision: str  # "BUY", "SELL", "HOLD"
    symbol: str
    market_type: str  # "SPOT", "DEX", "FUTURES"
    confidence: float
    reasoning: str
    parameters: Optional[Dict[str, Any]] = None  # TP, SL, Amount, etc.

class ExecutionResult(BaseModel):
    success: bool
    order_id: Optional[str] = None
    message: str
    details: Optional[Dict[str, Any]] = None
