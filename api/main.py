import logging
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from config import Config

# Configure logging
logging.basicConfig(level=Config.LOG_LEVEL)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 SignalKey Trading API iniciando...")
    yield
    logger.info("🛑 SignalKey Trading API cerrando...")

app = FastAPI(
    title="SignalKey Trading API",
    description="API para trading automatizado con análisis de IA",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Health check endpoint
@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "demo_mode": Config.DEMO_MODE,
        "exchange": Config.EXCHANGE_ID
    }

# Telegram webhook endpoint
@app.post("/webhook/telegram")
async def telegram_webhook(data: dict):
    """
    Recibe señales de Telegram y las procesa
    """
    try:
        logger.info(f"📡 Señal recibida: {data}")
        
        # Aquí se procesaría la señal con Gemini AI
        # y se ejecutaría la operación en CEX/DEX
        
        return {
            "status": "received",
            "message": "Señal procesada correctamente"
        }
    except Exception as e:
        logger.error(f"Error procesando señal: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))

# Generic webhook endpoint
@app.post("/webhook/signal")
async def signal_webhook(data: dict):
    """
    Recibe señales de cualquier fuente
    """
    try:
        logger.info(f"📡 Señal recibida: {data}")
        return {
            "status": "received",
            "message": "Señal procesada correctamente"
        }
    except Exception as e:
        logger.error(f"Error procesando señal: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))

# Backtesting endpoint
@app.post("/backtest")
async def run_backtest(symbol: str, days: int = 30, timeframe: str = "1h"):
    """
    Ejecuta un backtesting con datos históricos
    """
    try:
        logger.info(f"📊 Backtesting: {symbol} ({days} días, {timeframe})")
        
        # Aquí se ejecutaría el backtesting
        
        return {
            "status": "completed",
            "symbol": symbol,
            "days": days,
            "timeframe": timeframe,
            "results": {
                "total_trades": 0,
                "win_rate": 0,
                "profit_factor": 0,
                "max_drawdown": 0
            }
        }
    except Exception as e:
        logger.error(f"Error en backtesting: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))

# Configuration endpoint
@app.get("/config")
async def get_config():
    """
    Retorna la configuración actual
    """
    return {
        "demo_mode": Config.DEMO_MODE,
        "exchange": Config.EXCHANGE_ID,
        "has_gemini_key": bool(Config.GEMINI_API_KEY),
        "has_gmgn_key": bool(Config.GMGN_API_KEY),
        "has_telegram_token": bool(Config.TELEGRAM_BOT_TOKEN),
        "has_cex_credentials": bool(Config.CEX_API_KEY),
        "has_dex_wallet": bool(Config.DEX_WALLET_PRIVATE_KEY)
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=Config.API_HOST,
        port=Config.API_PORT,
        reload=True
    )
