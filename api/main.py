from fastapi import FastAPI, BackgroundTasks, Depends, HTTPException
from datetime import datetime
from api.src.domain.models.schemas import TradingSignal, AnalysisResult
from api.src.application.services.ai_service import AIService
from api.src.application.services.cex_service import CEXService
from api.src.application.services.dex_service import DEXService
from api.src.application.services.backtest_service import BacktestService
from api.src.application.services.bot_service import SignalBotService
from api.src.adapters.driven.persistence.mongodb import db, get_app_config
import logging
import asyncio
from typing import Optional
from bson import ObjectId

# Configuración de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from contextlib import asynccontextmanager
from api.src.infrastructure.telegram.telegram_bot import start_userbot, bot_instance
from api.src.infrastructure.telegram.telegram_bot_manager import bot_manager
from api.src.application.services.monitor_service import MonitorService
from fastapi.middleware.cors import CORSMiddleware
from api.config import Config

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("=== Starting SignalKey Platform Services (Hexagonal Mode) ===")
    
    bot_manager.signal_processor = process_signal_task
    
    try:
        await bot_manager.restart_all_bots(message_handler=process_signal_task)
        logger.info(f"Telegram Bot Manager started with {bot_manager.get_active_bots_count()} active bots")
        
        # --- TASK 7.2: Boot Manager Resilience ---
        # Reemplaza la lógica anterior con el nuevo BootManager más robusto
        from api.src.application.services.boot_manager import BootManager
        # Pasamos None como socket_service por ahora si no está disponible en scope global fácil o lo inyectamos después
        # Nota: main.py tiene imports en desorden, idealmente socket_service vendría de router o container
        boot_manager = BootManager(db_adapter_in=db) 
        await boot_manager.initialize_active_bots()
        # ----------------------------------------
    except Exception as e:
        logger.error(f"Error starting Telegram Bot Manager: {e}")

    from api.src.application.services.tracker_service import TrackerService
    global tracker_service, monitor_service
    tracker_service = TrackerService(cex_service=cex_service, dex_service=dex_service)
    await tracker_service.start_monitoring()
    
    from api.src.application.services.monitor_service import MonitorService
    monitor_service = MonitorService(cex_service=cex_service, dex_service=dex_service)
    monitor_task = asyncio.create_task(monitor_service.start_monitoring())

    bot_monitor_task = asyncio.create_task(signal_bot_service.monitor_bots())
    
    # --- Strategy Runner Auto-Trade Loop ---
    from api.src.application.services.strategy_runner_service import StrategyRunnerService
    from api.src.application.services.ml_service import MLService
    from api.src.adapters.driving.api.routers.bot_router import repo as bot_repo, engine
    
    # Initialize ML Service shared instance
    ml_service = MLService(exchange_adapter=ccxt_adapter)
    
    # Inject dependencies
    strategy_runner = StrategyRunnerService(bot_repo, ml_service, engine)
    await strategy_runner.start()
    
    logger.info("=== All services are running in background ===")
    
    yield
    
    # Shutdown
    logger.info("=== Stopping SignalKey Platform Services ===")
    await bot_instance.stop()
    await bot_manager.stop_all_bots()
    await monitor_service.stop_monitoring()
    monitor_task.cancel()
    bot_monitor_task.cancel()
    await strategy_runner.stop()
    await cex_service.close_all()
    await dex_service.close_all()
    await ai_service.close()
    logger.info("=== Shutdown complete ===")

app = FastAPI(title="Crypto Trading Signal API (Hexagonal Refactored)", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    # allow_origins=["*"],  # Wildcard is often problematic with credentials
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
        "http://localhost:3002",
        "http://127.0.0.1:3002",
        "https://psychic-guide-g4wr4jp4r4x93p45w-3000.app.github.dev" # Specific user origin
    ],
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?|https://.*\.app\.github\.dev",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Inicialización de servicios globales
from api.src.adapters.driven.exchange.ccxt_adapter import CcxtAdapter
ccxt_adapter = CcxtAdapter(db_adapter=db) # Initialize Adapter with DB

# Inyección de dependencia para servicios globalmente accesibles
from api.config import Config
logger.info(f"[INIT] JWT Secret prefix: {Config.JWT_SECRET[:4]}... (len: {len(Config.JWT_SECRET)})")

ai_service = AIService()
# Inject configured adapter into CEXService
cex_service = CEXService(ccxt_adapter=ccxt_adapter) 
dex_service = DEXService()
backtest_service = BacktestService(exchange_adapter=ccxt_adapter) # Use generic adapter for backtest
signal_bot_service = SignalBotService(cex_service=cex_service, dex_service=dex_service)

tracker_service = None
monitor_service = None

# Importar y agregar routers
from api.src.adapters.driving.api.routers.auth_router import router as auth_router
from api.src.adapters.driving.api.routers.user_config_router import router as config_router
from api.src.adapters.driving.api.routers.telegram_router import router as telegram_router
from api.src.adapters.driving.api.routers.backtest_router import router as backtest_router
from api.src.adapters.driving.api.routers.websocket_router import router as websocket_router
from api.src.adapters.driving.api.routers.ml_router import router as ml_router
from api.src.adapters.driving.api.routers.market_data_router import router as market_data_router
from api.src.adapters.driving.api.routers.bot_router import router as bot_router

app.include_router(auth_router)
app.include_router(config_router)
app.include_router(telegram_router)
app.include_router(backtest_router)
app.include_router(websocket_router)
app.include_router(ml_router)
app.include_router(market_data_router)
app.include_router(bot_router)

# --- Endpoints --- #

@app.post("/config/telegram_activate")
async def update_telegram_activate(user_id: str, active: bool):
    """
    Activa o desactiva el procesamiento de mensajes de Telegram.
    """
    try:
        user = await db.users.find_one({"openId": user_id})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
            
        await db.app_configs.update_one(
            {"userId": user["_id"]},
            {"$set": {"botTelegramActivate": active}}
        )
        return {"status": "success", "active": active}
    except Exception as e:
        logger.error(f"Error updating telegram config: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/status/{user_id}")
async def get_user_status(user_id: str):
    """
    Retorna el estado del sistema para un usuario específico.
    Usado por el Dashboard para mostrar información en tiempo real.
    """
    try:
        # Buscar usuario
        user = await db.users.find_one({"openId": user_id})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Obtener configuración
        config = await db.app_configs.find_one({"userId": user["_id"]})
        
        # Contar bots activos
        active_bots = await db.trades.count_documents({
            "userId": user["_id"],
            "status": "active"
        })
        
        # Contar señales recientes (últimas 24h)
        from datetime import datetime, timedelta
        recent_signals = await db.signals.count_documents({
            "userId": user["_id"],
            "createdAt": {"$gte": datetime.utcnow() - timedelta(hours=24)}
        })
        
        return {
            "user_id": user_id,
            "is_auto_enabled": config.get("isAutoEnabled", False) if config else False,
            "demo_mode": config.get("demoMode", True) if config else True,
            "active_bots": active_bots,
            "recent_signals_24h": recent_signals,
            "active_bots": active_bots,
            "recent_signals_24h": recent_signals,
            "telegram_connected": bool(config.get("telegramBotToken")) if config else False,
            "botTelegramActivate": config.get("botTelegramActivate", False) if config else False,
            "ai_provider": config.get("aiProvider", "gemini") if config else "gemini",
            "status": "online"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting status for {user_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

async def process_signal_task(signal: TradingSignal, user_id: str = "default_user"):
    """
    Refactored using Hexagonal Architecture.
    Delegates to the ProcessSignalUseCase via the DI Container.
    """
    logger.info(f"Procesando señal de {signal.source} para usuario {user_id} (Hexagonal)")
    
    from api.src.infrastructure.di.container import container
    
    # Obtener config del usuario
    config = await get_app_config(user_id)
    if not config:
        logger.warning(f"No config found for user {user_id}, using environment defaults")
        config = {}
        
    # Check Master Switch for Telegram
    if not config.get("botTelegramActivate", False):
        logger.info(f"Telegram processing disabled for user {user_id}. Signal ignored.")
        return

    # Ejecutar el caso de uso
    use_case = container.get_process_signal_use_case()
    try:
        await use_case.execute(
            raw_text=signal.raw_text,
            source=signal.source,
            user_id=user_id,
            config=config
        )
    except Exception as e:
        logger.error(f"Error in ProcessSignalUseCase: {e}")
