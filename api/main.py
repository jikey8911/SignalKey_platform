from fastapi import FastAPI, BackgroundTasks, Depends, HTTPException
from api.models.schemas import TradingSignal
from api.services.gemini_service import GeminiService
from api.services.cex_service import CEXService
from api.services.dex_service import DEXService
from api.services.backtest_service import BacktestService
from api.models.mongodb import db, get_app_config
import logging
from typing import Optional
from bson import ObjectId

# Configuración de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from contextlib import asynccontextmanager
from api.bot.telegram_bot import start_userbot, bot_instance
from fastapi.middleware.cors import CORSMiddleware

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting Telegram UserBot...")
    # Run in background to not block startup if auth is needed (though auth IS blocking for input)
    # Ideally, we start it as a task.
    import asyncio
    asyncio.create_task(start_userbot())
    yield
    # Shutdown
    logger.info("Stopping Telegram UserBot...")
    await bot_instance.stop()

app = FastAPI(title="Crypto Trading Signal API (MongoDB Refactored)", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173", "http://127.0.0.1:3000", "http://localhost:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Inicialización de servicios
gemini_service = GeminiService()
cex_service = CEXService()
dex_service = DEXService()
backtest_service = BacktestService()

async def process_signal_task(signal: TradingSignal, user_id: str = "default_user"):
    logger.info(f"Procesando señal de {signal.source} para usuario {user_id}")
    
    # Obtener config del usuario para ver si tiene Gemini API Key
    config = await get_app_config(user_id)
    gemini_key = config.get("geminiApiKey") if config else None
    
    # 1. Analizar con Gemini (inyectar API key si existe)
    analysis = await gemini_service.analyze_signal(signal.raw_text, api_key=gemini_key)
    logger.info(f"Análisis completado: {analysis.decision} para {analysis.symbol}")
    
    if analysis.decision == "HOLD":
        logger.info("Decisión: HOLD. No se ejecuta operación.")
        return

    # 2. Ejecutar operación
    if analysis.market_type == "DEX":
        result = await dex_service.execute_trade(analysis, user_id=user_id)
    else:
        result = await cex_service.execute_trade(analysis, user_id=user_id)
        
    logger.info(f"Resultado de ejecución: {'Éxito' if result.success else 'Fallo'} - {result.message}")

@app.post("/webhook/signal")
async def receive_signal(signal: TradingSignal, background_tasks: BackgroundTasks, user_id: Optional[str] = "default_user"):
    background_tasks.add_task(process_signal_task, signal, user_id)
    return {"status": "Signal received and processing in background"}

@app.get("/telegram/dialogs")
async def get_telegram_dialogs():
    """Returns list of channels/groups from the UserBot."""
    try:
        dialogs = await bot_instance.get_dialogs()
        return dialogs
    except Exception as e:
        logger.error(f"Error getting dialogs: {e}")
        return []

@app.get("/health")
async def health_check():
    return {"status": "healthy", "database": "mongodb"}

@app.get("/balances/{user_id}")
async def get_balances(user_id: str):
    user = await db.users.find_one({"openId": user_id})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    balances = await db.virtual_balances.find({"userId": user["_id"]}).to_list(length=100)
    return [{**b, "_id": str(b["_id"]), "userId": str(b["userId"])} for b in balances]

@app.get("/history/{user_id}")
async def get_history(user_id: str):
    user = await db.users.find_one({"openId": user_id})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    history = await db.trades.find({"userId": user["_id"]}).sort("createdAt", -1).limit(50).to_list(length=50)
    return [{**h, "_id": str(h["_id"]), "userId": str(h["userId"]), "signalId": str(h.get("signalId", ""))} for h in history]

from pydantic import BaseModel

class ConnectionTestRequest(BaseModel):
    exchangeId: str
    apiKey: str
    secret: str
    password: Optional[str] = None
    uid: Optional[str] = None

@app.post("/test-connection")
async def test_connection(data: ConnectionTestRequest):
    success, message = await cex_service.test_connection(
        data.exchangeId,
        data.apiKey,
        data.secret,
        data.password,
        data.uid
    )
    return {"success": success, "message": message}

if __name__ == "__main__":
    import uvicorn
    import os
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
