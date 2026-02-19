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
    is_safe: bool = True
    risk_score: float = 0.0
    parameters: Optional[Dict[str, Any]] = {
        "entry_price": None,
        "entry_type": "market", # "market" o "limit"
        "tp": [], # Lista de precios objetivo [{price: 1.0, percent: 50}]
        "sl": None,
        "leverage": 1,
        "network": None
    }

class ExecutionResult(BaseModel):
    success: bool
    order_id: Optional[str] = None
    message: str
    details: Optional[Dict[str, Any]] = None

# Nuevos esquemas para MongoDB y Configuración Dinámica

class ExchangeConfig(BaseModel):
    exchangeId: str = "okx"
    apiKey: str
    secret: str
    password: Optional[str] = None
    uid: Optional[str] = None
    isActive: bool = True

class DexConfig(BaseModel):
    walletPrivateKey: Optional[str] = None
    rpcUrl: str = "https://api.mainnet-beta.solana.com"

class BotStrategyConfig(BaseModel):
    maxActiveBots: int = 5
    maxActiveTelegramBots: int = 0  # 0 = sin límite
    tpLevels: int = 3 # Número de niveles de Take Profit
    tpPercent: float = 2.0 # Porcentaje de cambio para TP por defecto
    slPercent: float = 1.5 # Porcentaje de cambio para SL por defecto
    sellPercentPerTP: float = 33.3 # Porcentaje a vender en cada TP

class InvestmentLimits(BaseModel):
    cexMaxAmount: float = 100.0
    dexMaxAmount: float = 1.0

class AppConfigSchema(BaseModel):
    userId: Any # ObjectId
    isAutoEnabled: bool = True # Control maestro de procesos
    botTelegramActivate: bool = False # Control maestro de Telegram
    demoMode: bool = True
    geminiApiKey: Optional[str] = None
    openaiApiKey: Optional[str] = None
    perplexityApiKey: Optional[str] = None
    grokApiKey: Optional[str] = None
    groqApiKey: Optional[str] = None
    gmgnApiKey: Optional[str] = None
    zeroExApiKey: Optional[str] = None
    telegramBotToken: Optional[str] = None
    telegramChatId: Optional[str] = None
    
    # Telegram User Bot Config
    telegramApiId: Optional[str] = None
    telegramApiHash: Optional[str] = None
    telegramPhoneNumber: Optional[str] = None
    telegramSessionString: Optional[str] = None
    telegramIsConnected: bool = False
    telegramLastConnected: Optional[datetime] = None
    telegramChannels: Dict[str, List[str]] = Field(default_factory=lambda: {"allow": [], "deny": []})

    exchanges: List[ExchangeConfig] = []
    dexConfig: DexConfig = Field(default_factory=DexConfig)
    investmentLimits: InvestmentLimits = Field(default_factory=InvestmentLimits)
    virtualBalances: Dict[str, float] = Field(default_factory=lambda: {"cex": 10000.0, "dex": 10.0})
    botStrategy: BotStrategyConfig = Field(default_factory=BotStrategyConfig)
    createdAt: Optional[datetime] = None
    updatedAt: Optional[datetime] = None

class TradeSchema(BaseModel):
    userId: Any
    signalId: Optional[Any] = None
    symbol: str
    side: str
    entryPrice: float
    targetPrice: Optional[float] = None
    stopLoss: Optional[float] = None
    takeProfits: List[Dict[str, Any]] = []
    amount: float
    leverage: int = 1
    marketType: str
    isDemo: bool = True
    orderId: Optional[str] = None
    status: str = "pending" # "pending", "active", "completed", "failed", "cancelled"
    currentTPLevel: int = 0
    pnl: Optional[float] = None
    isSafe: bool = True
    createdAt: datetime = Field(default_factory=datetime.utcnow)
    executedAt: Optional[datetime] = None
    lastMonitoredAt: Optional[datetime] = None

class BotInstanceSchema(BaseModel):
    id: Optional[Any] = Field(alias="_id", default=None)
    user_id: Any
    name: str = "New Bot"
    symbol: str
    amount: float = Field(..., gt=0, description="Investment amount per trade. Mandatory.")
    strategy_name: str = "auto"
    timeframe: str = "15m"
    market_type: str = "spot" # spot, future
    status: str = "active" # active, paused, stopped
    mode: str = "simulated" # simulated, real
    side: Optional[str] = None # BUY, SELL
    position: Optional[Dict[str, float]] = Field(default_factory=lambda: {"qty": 0.0, "avg_price": 0.0})
    exchangeId: str = "okx"
    exchange_id: Optional[str] = Field(alias="exchangeId", default="okx") # Alias for compatibility
    createdAt: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        populate_by_name = True


class BotFeatureStateSchema(BaseModel):
    """Persisted feature snapshot/state per bot strategy."""

    id: Optional[Any] = Field(alias="_id", default=None)
    botId: Any
    userId: Any
    userOpenId: Optional[str] = None
    strategyName: str
    symbol: str
    exchangeId: str
    timeframe: str
    marketType: str = "spot"
    features: List[str] = Field(default_factory=list)
    latestFeatures: Dict[str, Optional[float]] = Field(default_factory=dict)
    # windowCandles: [{timestamp,open,high,low,close,volume,features:{...}}]
    windowCandles: List[Dict[str, Any]] = Field(default_factory=list)
    lastCandleTimestamp: Optional[str] = None
    featureRows: int = 0
    initializedAt: datetime = Field(default_factory=datetime.utcnow)
    createdAt: Optional[datetime] = None
    updatedAt: Optional[datetime] = None

    class Config:
        populate_by_name = True


class BotFeatureHistorySchema(BaseModel):
    id: Optional[Any] = Field(alias="_id", default=None)
    botId: Any
    userId: Any
    strategyName: str
    symbol: str
    exchangeId: str
    timeframe: str
    marketType: str = "spot"
    candleTs: str
    candle: Dict[str, Any] = Field(default_factory=dict)
    features: Dict[str, Optional[float]] = Field(default_factory=dict)
    createdAt: Optional[datetime] = None
    updatedAt: Optional[datetime] = None

    class Config:
        populate_by_name = True

# --- NUEVOS SCHEMAS PARA OPTIMIZACIÓN Y AGENTES IA ---

class AIAgent(BaseModel):
    id: Optional[Any] = Field(alias="_id", default=None)
    userId: Any # ObjectId or str
    configId: Any # ObjectId or str related to AppConfig
    provider: str # gemini, openai, perplexity, grok, groq
    apiKey: Optional[str] = None
    isActive: bool = False
    isPrimary: bool = False # Defines if this is the currently selected provider
    createdAt: datetime = Field(default_factory=datetime.utcnow)
    updatedAt: Optional[datetime] = None

    class Config:
        populate_by_name = True

class StrategyOptimizationRequest(BaseModel):
    """Request to ask the AI to review/optimize a strategy implementation.

    Notes:
    - Models (.pkl) still generate the signals in backtests.
    - This request is for *code review/refactor* of the strategy source.
    """

    strategy_name: str
    symbol: str
    timeframe: str
    market_type: str = "spot"
    days: int
    initial_balance: float

    # Backtest artifacts (can be supplied by frontend; if not, backend can regenerate).
    metrics: Dict[str, Any]  # win_rate, profit_pct, max_drawdown, total_trades, etc.
    trades: List[Dict[str, Any]]  # operations list (time, price, pnl, type...)
    candles: Optional[List[Dict[str, Any]]] = None  # OHLCV set used in the backtest (optional)
    decisions: Optional[List[Dict[str, Any]]] = None  # model decisions per candle (optional)
    holds: Optional[List[Dict[str, Any]]] = None  # optional list/summary of HOLD periods

    # Optional: raw code sent by frontend. If omitted, backend will load from strategies folder.
    source_code: Optional[str] = None

    # Optional: user feedback ("hazla más conservadora")
    user_feedback: Optional[str] = None


class StrategyOptimizeRunRequest(BaseModel):
    """Convenience request: backend runs a single-strategy backtest and then calls AI optimizer."""

    strategy_name: str
    symbol: str
    exchange_id: str = "okx"
    timeframe: str = "1h"
    market_type: str = "spot"
    days: int = 7
    initial_balance: float = 10000.0
    trade_amount: Optional[float] = None
    user_feedback: Optional[str] = None

class StrategyOptimizationResponse(BaseModel):
    original_code: str
    optimized_code: str
    analysis: str
    modifications: List[str]

    # Optional: AI-proposed expected improvements (to show side-by-side in UI)
    expected_profit_pct: Optional[float] = None
    expected_win_rate: Optional[float] = None

class SaveStrategyRequest(BaseModel):
    strategy_name: str
    code: str
    market_type: str = "spot" # spot, futures
    description: Optional[str] = None
