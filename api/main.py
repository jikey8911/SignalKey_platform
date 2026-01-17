from fastapi import FastAPI, BackgroundTasks, Depends, HTTPException
from datetime import datetime
from api.models.schemas import TradingSignal
from api.services.ai_service import AIService
from api.services.cex_service import CEXService
from api.services.dex_service import DEXService
from api.services.backtest_service import BacktestService
from api.models.mongodb import db, get_app_config
import logging
import asyncio
from typing import Optional
from bson import ObjectId

# Configuración de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from contextlib import asynccontextmanager
from api.bot.telegram_bot import start_userbot, bot_instance
from api.bot.telegram_bot_manager import bot_manager
from api.services.monitor_service import MonitorService
from fastapi.middleware.cors import CORSMiddleware

# monitor_service = MonitorService() # Se instanciará en lifespan

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("=== Starting SignalKey Platform Services ===")
    
    # Configurar el procesador de señales global para los bots
    bot_manager.signal_processor = process_signal_task
    
    # 1. Iniciar bots de Telegram de usuarios desde BD
    logger.info("Starting Telegram Bot Manager...")
    try:
        await bot_manager.restart_all_bots(message_handler=process_signal_task)
        logger.info(f"Telegram Bot Manager started with {bot_manager.get_active_bots_count()} active bots")
    except Exception as e:
        logger.error(f"Error starting Telegram Bot Manager: {e}")

    # 2. Iniciar Tracker de Trading (Monitoreo de señales)
    logger.info("Starting Tracker Service...")
    from api.services.tracker_service import TrackerService # Importar clase, no instancia
    global tracker_service, monitor_service
    tracker_service = TrackerService(cex_service=cex_service, dex_service=dex_service)
    await tracker_service.start_monitoring()
    
    # 3. Iniciar Monitor de Precios
    logger.info("Starting Price Monitor Service...")
    from api.services.monitor_service import MonitorService
    monitor_service = MonitorService(cex_service=cex_service)
    monitor_task = asyncio.create_task(monitor_service.start_monitoring())
    
    logger.info("=== All services are running in background ===")
    
    yield
    
    # Shutdown
    logger.info("=== Stopping SignalKey Platform Services ===")
    
    logger.info("Stopping Telegram UserBot...")
    await bot_instance.stop()
    
    logger.info("Stopping all user Telegram bots...")
    await bot_manager.stop_all_bots()
    
    logger.info("Stopping Price Monitor Service...")
    await monitor_service.stop_monitoring()
    monitor_task.cancel()
    
    logger.info("Closing CEX, DEX and AI sessions...")
    await cex_service.close_all()
    await dex_service.close_all()
    await ai_service.close()
    
    logger.info("=== Shutdown complete ===")

app = FastAPI(title="Crypto Trading Signal API (MongoDB Refactored)", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173", "http://127.0.0.1:3000", "http://localhost:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Inicialización de servicios globales
ai_service = AIService()
cex_service = CEXService()
dex_service = DEXService()
backtest_service = BacktestService()

# Placeholder para servicios que se instancian en lifespan
tracker_service = None
monitor_service = None

# Importar y agregar routers
from api.routers.telegram_router import router as telegram_router
app.include_router(telegram_router)

async def process_signal_task(signal: TradingSignal, user_id: str = "default_user"):
    logger.info(f"Procesando señal de {signal.source} para usuario {user_id}")
    
    # 0. Crear registro inicial de la señal en la DB
    user = await db.users.find_one({"openId": user_id})
    if not user:
        logger.error(f"User {user_id} not found")
        return

    signal_id = await db.trading_signals.insert_one({
        "userId": user["_id"],
        "source": signal.source,
        "rawText": signal.raw_text,
        "status": "processing", # Estado: La AI la está procesando
        "createdAt": datetime.utcnow()
    })
    inserted_id = signal_id.inserted_id
    
    # EMITIR POR SOCKET
    await socket_service.emit_to_user(user_id, "signal_update", {
        "id": str(inserted_id),
        "source": signal.source,
        "raw_text": signal.raw_text,
        "status": "processing",
        "createdAt": datetime.utcnow().isoformat()
    })
    
    # Obtener config del usuario para ver la configuración de IA
    config = await get_app_config(user_id)
    
    # Log de la configuración de IA
    if config:
        # Verificar si el procesamiento automático está habilitado
        if not config.get("isAutoEnabled", True):
            logger.info(f"Auto-processing is DISABLED for user {user_id}. Aborting signal processing.")
            await db.trading_signals.update_one(
                {"_id": inserted_id},
                {"$set": {"status": "cancelled", "executionMessage": "Auto-processing disabled by user"}}
            )
            return

        ai_provider = config.get("aiProvider", "gemini")
        has_api_key = bool(config.get("aiApiKey") or config.get("geminiApiKey"))
        logger.info(f"Config retrieved for user {user_id}: aiProvider={ai_provider}, has_api_key={has_api_key}")
    else:
        logger.warning(f"No config found for user {user_id}, will use environment defaults")
    
    # 1. Analizar con el servicio de IA (Aprobación de la IA obligatoria)
    try:
        analysis = await ai_service.analyze_signal(signal.raw_text, config=config)
        logger.info(f"AI Analysis completed: {analysis.decision} for {analysis.symbol} (confidence: {analysis.confidence})")
        
        # Actualizar señal con el análisis
        await db.trading_signals.update_one(
            {"_id": inserted_id},
            {"$set": {
                "decision": analysis.decision,
                "symbol": analysis.symbol,
                "marketType": analysis.market_type,
                "confidence": analysis.confidence,
                "reasoning": analysis.reasoning,
                "status": "accepted" if analysis.decision != "HOLD" else "rejected"
            }}
        )
    except Exception as e:
        logger.error(f"Error analyzing signal: {e}")
        await db.trading_signals.update_one(
            {"_id": inserted_id},
            {"$set": {"status": "error", "reasoning": str(e)}}
        )
        return
    
    # Si la IA decide HOLD, no se aprueba la señal para ejecución
    if analysis.decision == "HOLD":
        logger.info(f"Señal RECHAZADA por la IA: {analysis.reasoning}")
        return

    # 2. Validar Seguridad (Honeypot/Riesgo)
    if not analysis.is_safe:
        logger.warning(f"Señal MARCADA COMO INSEGURA por la IA (Score: {analysis.risk_score}): {analysis.reasoning}")
        await db.trading_signals.update_one(
            {"_id": inserted_id},
            {"$set": {"status": "rejected_unsafe", "riskScore": analysis.risk_score}}
        )
        # EMITIR POR SOCKET
        await socket_service.emit_to_user(user_id, "signal_update", {
            "id": str(inserted_id),
            "status": "rejected_unsafe",
            "riskScore": analysis.risk_score,
            "reasoning": analysis.reasoning
        })
        return

    # 3. Preparar para Supervisión (No ejecutar inmediatamente si es 'limit' o necesita monitoreo)
    logger.info(f"Señal APROBADA por la IA: {analysis.decision} {analysis.symbol}")
    await db.trading_signals.update_one({"_id": inserted_id}, {"$set": {"status": "monitoring"}})
    
    try:
        # Obtener límites de inversión para crear el trade document
        max_amount = config.get("investmentLimits", {}).get("cexMaxAmount" if analysis.market_type == "CEX" else "dexMaxAmount", 100.0)
        suggested_amount = analysis.parameters.get('amount', 0)
        amount = min(suggested_amount, max_amount) if suggested_amount > 0 else max_amount

        # Crear documento de Trade en estado 'monitoring'
        trade_data = {
            "userId": user["_id"],
            "signalId": inserted_id,
            "symbol": analysis.symbol,
            "side": analysis.decision,
            "entryPrice": analysis.parameters.get("entry_price") or 0.0,
            "targetPrice": analysis.parameters.get("entry_price"),
            "stopLoss": analysis.parameters.get("sl"),
            "takeProfits": analysis.parameters.get("tp", []),
            "amount": amount,
            "leverage": analysis.parameters.get("leverage", 1),
            "marketType": analysis.market_type,
            "isDemo": config.get("demoMode", True),
            "status": "monitoring",
            "isSafe": analysis.is_safe,
            "createdAt": datetime.utcnow()
        }
        
        result = await db.trades.insert_one(trade_data)
        trade_id = str(result.inserted_id)
        
        # Notificar al TrackerService para que inicie el monitoreo
        from api.services.tracker_service import tracker_service
        await tracker_service.add_trade_to_monitor(trade_id)
        
        logger.info(f"Trade {trade_id} enviado a TrackerService para supervisión dinámica")
        
        # Actualizar estado final de la señal a 'monitoring'
        await db.trading_signals.update_one({"_id": inserted_id}, {"$set": {"status": "monitoring"}})
        
        # EMITIR POR SOCKET
        await socket_service.emit_to_user(user_id, "signal_update", {
            "id": str(inserted_id),
            "status": "monitoring",
            "symbol": analysis.symbol,
            "decision": analysis.decision
        })
            
    except Exception as e:
        logger.error(f"Error executing trade: {e}")
        await db.trading_signals.update_one(
            {"_id": inserted_id},
            {"$set": {"status": "failed", "executionMessage": str(e)}}
        )

@app.post("/webhook/signal")
async def receive_signal(signal: TradingSignal, background_tasks: BackgroundTasks, user_id: Optional[str] = "default_user"):
    background_tasks.add_task(process_signal_task, signal, user_id)
    return {"status": "Signal received and processing in background"}

# --- WebSocket Endpoint ---
from api.services.socket_service import socket_service
from fastapi import WebSocket, WebSocketDisconnect

@app.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str):
    logger.info(f"Incoming WebSocket connection attempt for user: {user_id}")
    await socket_service.connect(websocket, user_id)
    try:
        while True:
            # Mantener la conexión abierta y escuchar posibles mensajes del cliente
            data = await websocket.receive_text()
            # Opcional: Procesar mensajes enviados por el cliente
            logger.info(f"Message received from client {user_id}: {data}")
    except WebSocketDisconnect:
        socket_service.disconnect(websocket, user_id)
    except Exception as e:
        logger.error(f"WebSocket error for user {user_id}: {e}")
        socket_service.disconnect(websocket, user_id)

@app.get("/telegram/dialogs")
async def get_telegram_dialogs():
    """Returns list of channels/groups from the UserBot."""
    try:
        dialogs = await bot_instance.get_dialogs()
        return dialogs
    except Exception as e:
        logger.error(f"Error getting dialogs: {e}")
        return []

@app.get("/telegram/logs")
async def get_telegram_logs(limit: int = 50):
    try:
        cursor = db.telegram_logs.find({}).sort("timestamp", -1).limit(limit)
        logs = await cursor.to_list(length=limit)
        # Convert ObjectId and datetime to string safely
        formatted_logs = []
        for log in logs:
            log_item = {**log, "_id": str(log["_id"])}
            ts = log.get("timestamp")
            if isinstance(ts, datetime):
                log_item["timestamp"] = ts.isoformat()
            else:
                log_item["timestamp"] = str(ts) # Ya es string o algo parseable
            formatted_logs.append(log_item)
        return formatted_logs
    except Exception as e:
        logger.error(f"Error fetching logs: {e}")
        return []

@app.post("/balances/init/{user_id}")
async def initialize_balances(user_id: str):
    """Initialize virtual balances from config"""
    try:
        config = await get_app_config(user_id)
        if not config:
            raise HTTPException(status_code=404, detail="Config not found")
        
        virtual_balances = config.get("virtualBalances", {"cex": 10000, "dex": 10})
        
        # Initialize CEX balance
        await update_virtual_balance(user_id, "CEX", "USDT", virtual_balances.get("cex", 10000))
        
        # Initialize DEX balance
        await update_virtual_balance(user_id, "DEX", "SOL", virtual_balances.get("dex", 10))
        
        return {"success": True, "message": "Balances initialized", "balances": virtual_balances}
    except Exception as e:
        logger.error(f"Error initializing balances: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/status/{user_id}")
async def get_connection_status(user_id: str):
    """Check connection status for all services"""
    status = {
        "gemini": False,
        "exchange": False,
        "telegram": False,
        "gmgn": False
    }
    
    try:
        config = await get_app_config(user_id)
        if not config:
            return status
        
        # Check AI Provider
        if config.get("aiApiKey"):
            status["gemini"] = True # Mantenemos el nombre de la clave para compatibilidad o actualizamos el frontend
        
        # Check Exchange
        exchanges = config.get("exchanges", [])
        active_ex = next((e for e in exchanges if e.get("isActive") and e.get("apiKey")), None)
        if active_ex:
            try:
                exchange, _ = await cex_service.get_exchange_instance(user_id, active_ex["exchangeId"])
                if exchange:
                    status["exchange"] = True
            except:
                pass
        
        # Check Telegram
        if bot_manager.is_bot_active(user_id):
            status["telegram"] = True
        
        # Check GMGN
        if config.get("gmgnApiKey"):
            status["gmgn"] = True
        
        return status
    except Exception as e:
        logger.error(f"Error checking status: {e}")
        return status

@app.get("/health")
async def health_check():
    return {"status": "healthy", "database": "mongodb"}

@app.get("/balances/{user_id}")
async def get_balances(user_id: str):
    user = await db.users.find_one({"openId": user_id})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # 1. Get Config for keys
    config = await get_app_config(user_id)
    
    # 2. Get Real CEX Balance (if configured)
    cex_balance = 0.0
    if config:
        # Try primary exchange
        exchanges = config.get("exchanges", [])
        active_ex = next((e for e in exchanges if e.get("isActive")), None)
        if active_ex:
             # Reuse CEXService instance method if possible, or manual call
             # For speed/simplicity here, we use the service's helper
             # But the service helper requires 'get_exchange_instance' which caches
             try:
                 exchange, _ = await cex_service.get_exchange_instance(user_id, active_ex["exchangeId"])
                 if exchange:
                     # Fetch total balance in USDT
                     bal = await exchange.fetch_balance()
                     # Calculate total USDT value roughly
                     if 'total' in bal:
                         cex_balance = bal['total'].get('USDT', 0.0)
                         # Add other assets value? Complex. For now, just USDT.
             except Exception as e:
                 logger.error(f"Error fetching real balance: {e}")

    # 3. Get DB Balances (Virtual/Tracked)
    balances = await db.virtual_balances.find({"userId": user["_id"]}).to_list(length=100)
    
    # Merge/Override CEX balance if exists in DB or add it
    # We want to return a list that the frontend understands
    
    response_list = []
    
    # Add CEX if present
    cex_db = next((b for b in balances if b["marketType"] == "CEX"), None)
    if cex_db:
         response_list.append({**cex_db, "_id": str(cex_db["_id"]), "userId": str(cex_db["userId"]), "realBalance": cex_balance})
    else:
         # If no CEX balance in DB, inject one with the real balance finding
         response_list.append({
             "_id": "virtual_cex", 
             "userId": user_id, 
             "marketType": "CEX", 
             "currency": "USDT", 
             "amount": 0.0, # Virtual
             "realBalance": cex_balance
         })

    # Add DEX if present
    dex_db = next((b for b in balances if b["marketType"] == "DEX"), None)
    if dex_db:
        response_list.append({**dex_db, "_id": str(dex_db["_id"]), "userId": str(dex_db["userId"])})
    else:
         response_list.append({
             "_id": "virtual_dex",
             "userId": user_id,
             "marketType": "DEX",
             "currency": "SOL",
             "amount": 0.0
         })

    return response_list

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
    # Aseguramos que el puerto sea el que espera el frontend (8000)
    uvicorn.run(app, host="0.0.0.0", port=8000)
