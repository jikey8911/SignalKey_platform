from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime

class TradingSignal(BaseModel):
    source: str  # e.g., "telegram", "webhook"
    raw_text: str
    metadata: Optional[Dict[str, Any]] = None

class AnalysisResult(BaseModel):
    decision: str  # "BUY", "SELL", "HOLD"
    symbol: str
    market_type: str  # "CEX", "DEX"
    confidence: float
    reasoning: str
    parameters: Optional[Dict[str, Any]] = None  # TP, SL, Amount, etc.

class ExecutionResult(BaseModel):
    success: bool
    order_id: Optional[str] = None
    message: str
    details: Optional[Dict[str, Any]] = None

# Nuevos esquemas para MongoDB y Configuración Dinámica

class ExchangeConfig(BaseModel):
    exchangeId: str = "binance"
    apiKey: str
    secret: str
    password: Optional[str] = None
    uid: Optional[str] = None
    isActive: bool = True

class DexConfig(BaseModel):
    walletPrivateKey: Optional[str] = None
    rpcUrl: str = "https://api.mainnet-beta.solana.com"

class InvestmentLimits(BaseModel):
    cexMaxAmount: float = 100.0
    dexMaxAmount: float = 1.0

class AppConfigSchema(BaseModel):
    userId: Any # ObjectId
    demoMode: bool = True
    geminiApiKey: Optional[str] = None
    gmgnApiKey: Optional[str] = None
    telegramBotToken: Optional[str] = None
    telegramChatId: Optional[str] = None
    exchanges: List[ExchangeConfig] = []
    dexConfig: DexConfig = Field(default_factory=DexConfig)
    investmentLimits: InvestmentLimits = Field(default_factory=InvestmentLimits)
    createdAt: Optional[datetime] = None
    updatedAt: Optional[datetime] = None

class TradeSchema(BaseModel):
    userId: Any
    signalId: Optional[Any] = None
    symbol: str
    side: str
    price: float
    amount: float
    marketType: str
    isDemo: bool = True
    orderId: Optional[str] = None
    status: str = "pending"
    pnl: Optional[float] = None
    createdAt: datetime = Field(default_factory=datetime.utcnow)
    executedAt: Optional[datetime] = None
