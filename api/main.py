from fastapi import FastAPI, BackgroundTasks, Depends, HTTPException
from datetime import datetime
from api.models.schemas import TradingSignal, AnalysisResult
from api.services.ai_service import AIService
from api.services.cex_service import CEXService
from api.services.dex_service import DEXService
from api.services.backtest_service import BacktestService
from api.services.signal_bot_service import SignalBotService
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
from api.config import Config

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("=== Starting SignalKey Platform Services (Hexagonal Mode) ===")
    
    bot_manager.signal_processor = process_signal_task
    
    try:
        await bot_manager.restart_all_bots(message_handler=process_signal_task)
        logger.info(f"Telegram Bot Manager started with {bot_manager.get_active_bots_count()} active bots")
    except Exception as e:
        logger.error(f"Error starting Telegram Bot Manager: {e}")

    from api.services.tracker_service import TrackerService
    global tracker_service, monitor_service
    tracker_service = TrackerService(cex_service=cex_service, dex_service=dex_service)
    await tracker_service.start_monitoring()
    
    from api.services.monitor_service import MonitorService
    monitor_service = MonitorService(cex_service=cex_service, dex_service=dex_service)
    monitor_task = asyncio.create_task(monitor_service.start_monitoring())

    bot_monitor_task = asyncio.create_task(signal_bot_service.monitor_bots())
    
    logger.info("=== All services are running in background ===")
    
    yield
    
    # Shutdown
    logger.info("=== Stopping SignalKey Platform Services ===")
    await bot_instance.stop()
    await bot_manager.stop_all_bots()
    await monitor_service.stop_monitoring()
    monitor_task.cancel()
    bot_monitor_task.cancel()
    await cex_service.close_all()
    await dex_service.close_all()
    await ai_service.close()
    logger.info("=== Shutdown complete ===")

app = FastAPI(title="Crypto Trading Signal API (Hexagonal Refactored)", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Inicialización de servicios globales
ai_service = AIService()
cex_service = CEXService()
dex_service = DEXService()
backtest_service = BacktestService()
signal_bot_service = SignalBotService(cex_service=cex_service, dex_service=dex_service)

tracker_service = None
monitor_service = None

# Importar y agregar routers
from api.routers.telegram_router import router as telegram_router
from api.routers.backtest_router import router as backtest_router
app.include_router(telegram_router)
app.include_router(backtest_router)

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
