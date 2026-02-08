from fastapi import FastAPI, BackgroundTasks, Depends, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from datetime import datetime
import logging
import asyncio
import os
from contextlib import asynccontextmanager
from typing import Optional

# Imports internos
from api.src.domain.models.schemas import TradingSignal
from api.src.application.services.ai_service import AIService
from api.src.application.services.cex_service import CEXService
from api.src.application.services.dex_service import DEXService
from api.src.application.services.backtest_service import BacktestService
from api.src.application.services.bot_service import SignalBotService
from api.src.adapters.driven.persistence.mongodb import db, get_app_config
from api.src.infrastructure.telegram.telegram_bot_manager import bot_manager
from api.src.application.services.monitor_service import MonitorService
from api.src.application.services.tracker_service import TrackerService
from fastapi.middleware.cors import CORSMiddleware
from api.config import Config

# Configuración de logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger("API_MAIN")

# --- VARIABLES GLOBALES ---
# Se inicializan vacías y se rellenan en el startup
tracker_service = None
monitor_service = None
boot_task = None # Referencia para evitar Garbage Collection de la tarea

# --- FUNCIÓN DE ARRANQUE EN SEGUNDO PLANO (NO BLOQUEANTE) ---
async def run_background_startup():
    """
    Ejecuta las tareas pesadas (Telegram, Carga de Modelos, Bots) en paralelo
    después de que la API ya está respondiendo.
    """
    logger.info("⏳ [BACKGROUND] Iniciando secuencia de carga de servicios...")
    
    # Esperar un momento para asegurar que el loop principal respira
    await asyncio.sleep(2)

    try:
        # 1. Telegram Bots (Puede tardar por conexión de red)
        bot_manager.signal_processor = process_signal_task
        logger.info("🤖 [BACKGROUND] Iniciando Telegram Bot Manager...")
        await bot_manager.restart_all_bots(message_handler=process_signal_task)
        logger.info(f"✅ [BACKGROUND] Telegram activo: {bot_manager.get_active_bots_count()} bots.")

        # 2. Inicializar Bots de Trading (Recuperar estado de DB)
        from api.src.application.services.boot_manager import BootManager
        boot_manager_service = BootManager(db_adapter_in=db)
        logger.info("📈 [BACKGROUND] Reactivando bots de trading...")
        await boot_manager_service.initialize_active_bots()
        
        # 3. Cargar Modelos IA (Pesado en CPU/RAM)
        try:
            from api.src.infrastructure.ai.model_manager import ModelManager
            logger.info("🧠 [BACKGROUND] Cargando modelos de IA...")
            # Ejecutar en thread pool para no bloquear el loop async si usa joblib
            await asyncio.to_thread(ModelManager().load_all_models)
            logger.info("✅ [BACKGROUND] Modelos cargados.")
        except Exception as e:
            logger.warning(f"⚠️ [BACKGROUND] IA Model Manager warning: {e}")

        # 4. Iniciar Motores de Trading
        logger.info("🚀 [BACKGROUND] Arrancando motores de ejecución...")
        
        # Servicios globales (tracker, monitor)
        global tracker_service, monitor_service
        tracker_service = TrackerService(cex_service=cex_service, dex_service=dex_service)
        monitor_service = MonitorService(cex_service=cex_service, dex_service=dex_service)
        
        # Iniciar tareas asíncronas
        asyncio.create_task(monitor_service.start_monitoring())
        await signal_bot_service.start()
        
        logger.info("🎉 [BACKGROUND] SISTEMA COMPLETAMENTE OPERATIVO")

    except Exception as e:
        logger.error(f"❌ [BACKGROUND] Error crítico en arranque diferido: {e}", exc_info=True)

# --- LIFESPAN (EVENTOS DE CICLO DE VIDA) ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # === STARTUP ===
    logger.info("⚡ API iniciando...")
    
    # Lanzar la carga pesada como tarea independiente
    global boot_task
    boot_task = asyncio.create_task(run_background_startup())
    
    yield # Aquí la API empieza a recibir peticiones
    
    # === SHUTDOWN ===
    logger.info("🛑 API deteniéndose...")
    try:
        if boot_task: boot_task.cancel()
        await bot_manager.stop_all_bots()
        if monitor_service: await monitor_service.stop_monitoring()
        await signal_bot_service.stop()
        await cex_service.close_all()
        await dex_service.close_all()
        await ai_service.close()
    except Exception as e:
        logger.error(f"Error en shutdown: {e}")
    logger.info("👋 Shutdown completo.")

app = FastAPI(title="SignalKey Platform API", lifespan=lifespan)

# --- MIDDLEWARE & CONFIG ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Permitir todo para desarrollo local fácil
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Inicialización de adaptadores base (Ligeros)
from api.src.adapters.driven.exchange.ccxt_adapter import CcxtAdapter
ccxt_adapter = CcxtAdapter(db_adapter=db) 

logger.info(f"[INIT] Config loaded. JWT Prefix: {Config.JWT_SECRET[:4]}...")

# Instanciación de Servicios (Sin iniciarlos aún)
ai_service = AIService()
cex_service = CEXService(ccxt_adapter=ccxt_adapter) 
dex_service = DEXService()
backtest_service = BacktestService(exchange_adapter=ccxt_adapter) 
signal_bot_service = SignalBotService(cex_service=cex_service, dex_service=dex_service)

# --- ROUTERS ---
from fastapi import APIRouter

logger.info("📦 Cargando routers de la API...")

from api.src.adapters.driving.api.routers import auth_router
logger.info("  - Auth router [OK]")

from api.src.adapters.driving.api.routers import user_config_router
logger.info("  - User Config router [OK]")

from api.src.adapters.driving.api.routers import bot_router
logger.info("  - Bot router [OK]")

from api.src.adapters.driving.api.routers import market_data_router
logger.info("  - Market Data router [OK]")

from api.src.adapters.driving.api.routers import signal_router
logger.info("  - Signal router [OK]")

from api.src.adapters.driving.api.routers import trade_router
logger.info("  - Trade router [OK]")

from api.src.adapters.driving.api.routers import ml_router
logger.info("  - ML router [OK]")

from api.src.adapters.driving.api.routers import backtest_router
logger.info("  - Backtest router [OK]")

from api.src.adapters.driving.api.routers import telegram_router
logger.info("  - Telegram router [OK]")

from api.src.adapters.driving.api.routers import websocket_router
logger.info("  - WebSocket router [OK]")

from api.src.adapters.driving.api.routers import health_router
logger.info("  - Health router [OK]")

from api.src.adapters.driving.api.routers import ai_router
logger.info("  - AI router [OK]")

logger.info("✅ Todos los routers cargados.")

# API Router (prefix /api)
api_router = APIRouter(prefix="/api")
api_router.include_router(auth_router.router)
api_router.include_router(user_config_router.router)
api_router.include_router(telegram_router.router)
api_router.include_router(backtest_router.router)
api_router.include_router(ml_router.router)
api_router.include_router(market_data_router.router)
api_router.include_router(bot_router.router)
api_router.include_router(signal_router.router)
api_router.include_router(trade_router.router)
api_router.include_router(health_router.router)
api_router.include_router(ai_router.router)

app.include_router(api_router)

# WebSocket Router (Root level /ws)
app.include_router(websocket_router.router)

# --- TAREA DE PROCESAMIENTO DE SEÑALES ---
async def process_signal_task(signal: TradingSignal, user_id: str = "default_user"):
    from api.src.infrastructure.di.container import container
    try:
        use_case = container.get_process_signal_use_case()
        
        if user_id == "ALL":
            # Lógica simplificada para broadcast
            configs = await db.app_configs.find({"botTelegramActivate": True}).to_list(100)
            for cfg in configs:
                uid = str(cfg.get("userId")) # Simplificado, idealmente obtener openId
                # Enviar a background para no bloquear el loop del bot
                asyncio.create_task(use_case.execute(signal.raw_text, signal.source, uid, cfg))
            return

        config = await get_app_config(user_id) or {}
        if config.get("botTelegramActivate", False):
            await use_case.execute(signal.raw_text, signal.source, user_id, config)
            
    except Exception as e:
        logger.error(f"Error procesando señal: {e}")

# --- ENDPOINTS AUXILIARES ---
@app.get("/status/{user_id}")
async def get_user_status(user_id: str):
    # Implementación simplificada para health check rápido
    return {"status": "online", "user_id": user_id, "system_booting": boot_task is not None and not boot_task.done()}

# --- SERVIR FRONTEND ---
frontend_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "web", "dist", "public")
# Fallback si public no existe (a veces vite construye directo en dist)
if not os.path.exists(frontend_path):
    frontend_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "web", "dist")

if os.path.exists(frontend_path):
    logger.info(f"📂 Frontend estático detectado en: {frontend_path}")
    app.mount("/assets", StaticFiles(directory=os.path.join(frontend_path, "assets")), name="assets")
    
    @app.get("/{full_path:path}")
    async def serve_react_app(full_path: str):
        file_path = os.path.join(frontend_path, full_path)
        if os.path.exists(file_path) and os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse(os.path.join(frontend_path, "index.html"))
else:
    logger.warning("⚠️ Frontend build NO encontrado. Ejecuta 'npm run build' en la carpeta web.")

# --- BLOQUE DE EJECUCIÓN (SOLUCIONA EL CIERRE PREMATURO) ---
if __name__ == "__main__":
    import uvicorn
    logger.info("🚀 Iniciando servidor Uvicorn...")
    uvicorn.run(
        "api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        workers=1,
        log_level="info"
    )