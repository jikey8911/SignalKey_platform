from fastapi import FastAPI, BackgroundTasks, Depends, HTTPException
from crypto_bot_api.models.schemas import TradingSignal
from crypto_bot_api.services.gemini_service import GeminiService
from crypto_bot_api.services.cex_service import CEXService
from crypto_bot_api.services.dex_service import DEXService
from crypto_bot_api.services.backtest_service import BacktestService
from crypto_bot_api.models.mongodb import db, get_app_config
import logging
from typing import Optional
from bson import ObjectId

# Configuración de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Crypto Trading Signal API (MongoDB Refactored)")

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

if __name__ == "__main__":
    import uvicorn
    import os
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
