from fastapi import FastAPI, BackgroundTasks
from crypto_bot_api.models.schemas import TradingSignal
from crypto_bot_api.services.gemini_service import GeminiService
from crypto_bot_api.services.cex_service import CEXService
from crypto_bot_api.services.dex_service import DEXService
from crypto_bot_api.services.backtest_service import BacktestService
from crypto_bot_api.models.database import init_db, SessionLocal, VirtualBalance, TradeHistory
import logging

# Inicializar DB
init_db()

# Configuración de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Crypto Trading Signal API")

# Inicialización de servicios
gemini_service = GeminiService()
cex_service = CEXService()
dex_service = DEXService()
backtest_service = BacktestService()

async def process_signal_task(signal: TradingSignal):
    logger.info(f"Procesando señal de {signal.source}")
    
    # 1. Analizar con Gemini
    analysis = await gemini_service.analyze_signal(signal.raw_text)
    logger.info(f"Análisis completado: {analysis.decision} para {analysis.symbol}")
    
    if analysis.decision == "HOLD":
        logger.info("Decisión: HOLD. No se ejecuta operación.")
        return

    # 2. Ejecutar operación
    if analysis.market_type == "DEX":
        result = await dex_service.execute_trade(analysis)
    else:
        result = await cex_service.execute_trade(analysis)
        
    logger.info(f"Resultado de ejecución: {'Éxito' if result.success else 'Fallo'} - {result.message}")

@app.post("/webhook/signal")
async def receive_signal(signal: TradingSignal, background_tasks: BackgroundTasks):
    background_tasks.add_task(process_signal_task, signal)
    return {"status": "Signal received and processing in background"}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

@app.get("/demo/balance")
async def get_demo_balance():
    db = SessionLocal()
    balances = db.query(VirtualBalance).all()
    result = {b.market_type + "_" + b.asset: b.amount for b in balances}
    db.close()
    return result

@app.get("/demo/history")
async def get_demo_history():
    db = SessionLocal()
    history = db.query(TradeHistory).order_by(TradeHistory.timestamp.desc()).limit(50).all()
    db.close()
    return history

@app.get("/backtest/{symbol}")
async def run_backtest(symbol: str, days: int = 7):
    # Reemplazar / por _ para el path si es necesario
    clean_symbol = symbol.replace("-", "/")
    result = await backtest_service.run_backtest(clean_symbol, days=days)
    return result

if __name__ == "__main__":
    import uvicorn
    from crypto_bot_api.config import Config
    uvicorn.run(app, host="0.0.0.0", port=Config.PORT)
