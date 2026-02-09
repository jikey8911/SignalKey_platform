from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from typing import Dict, Any
import logging
import json

# Imports de tus servicios (Ajusta las rutas según tu estructura real)
from api.src.adapters.driven.notifications.socket_service import SocketService
from api.src.domain.ports.output.BotRepository import IBotRepository
from api.src.domain.ports.output.signal_repository import ISignalRepository
# from api.src.domain.ports.output.trade_repository import TradeRepository 

logger = logging.getLogger(__name__)

router = APIRouter()

# Instancias globales o inyectadas
socket_manager = SocketService() # Tu manejador de conexiones
# Necesitarás una forma de obtener estos repositorios dentro del socket, 
# a menudo usando un contenedor de inyección de dependencias o instanciándolos aquí si son simples.
# bot_repo = BotRepository(...) 

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await socket_manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            
            action = message.get("action")
            
            if action == "SUBSCRIBE_BOT":
                bot_id = message.get("bot_id")
                if bot_id:
                    await handle_bot_subscription(websocket, bot_id)
            
            elif action == "UNSUBSCRIBE_BOT":
                bot_id = message.get("bot_id")
                if bot_id:
                    await handle_bot_unsubscription(websocket, bot_id)

            elif action == "PING":
                await websocket.send_json({"type": "PONG"})

    except WebSocketDisconnect:
        socket_manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"Error en websocket: {e}")
        try:
            await websocket.close()
        except:
            pass

async def handle_bot_subscription(websocket: WebSocket, bot_id: str):
    """
    1. Obtiene datos completos del bot.
    2. Envía SNAPSHOT al cliente.
    3. Suscribe al cliente a los topics de actualizaciones.
    """
    logger.info(f"Cliente suscribiéndose al bot {bot_id}")
    
    # A) OBTENER DATOS (Simulado - conecta con tus repositorios reales)
    # bot = await bot_repo.get_by_id(bot_id)
    # signals = await signal_repo.get_recent_by_bot(bot_id, limit=50)
    # positions = await trade_repo.get_open_positions(bot_id)
    
    # --- Datos Mock simulando la DB del Bot ---
    # Recuperamos la configuración vital: Exchange, Symbol, Timeframe
    bot_mock_config = {
        "id": bot_id,
        "name": "Bot Trading V1",
        "symbol": "BTC/USDT",       # Símbolo
        "timeframe": "1m",          # Temporalidad
        "exchange_id": "binance",   # Exchange específico (IMPORTANTE)
        "status": "running",
        "strategy": "RSI_Reversion_V2"
    }

    snapshot_data = {
        "type": "bot_snapshot",
        "bot_id": bot_id,
        "config": bot_mock_config,
        "positions": [
            # Ejemplo: Consultar DB de posiciones abiertas
            {"symbol": "BTC/USDT", "side": "LONG", "entryPrice": 64500, "amount": 0.01, "unrealizedPnL": 1.5}
        ],
        "signals": [
            # Ejemplo: Consultar DB de señales históricas
            {"type": "BUY", "price": 64000, "timestamp": 1709900000000, "status": "EXECUTED"},
            {"type": "SELL", "price": 65000, "timestamp": 1709910000000, "status": "EXECUTED"}
        ]
    }
    
    # B) ENVIAR SNAPSHOT
    await websocket.send_json(snapshot_data)
    
    # C) GESTIONAR SUSCRIPCIÓN EN EL SOCKET MANAGER
    # 1. Suscribir a eventos del bot (señales, alertas)
    await socket_manager.subscribe_to_topic(websocket, topic=f"bot:{bot_id}")
    
    # 2. Suscribir a datos de mercado (Velas en tiempo real)
    # Usamos exchange_id + symbol + timeframe para identificar el stream único
    exchange_id = bot_mock_config.get("exchange_id")
    symbol = bot_mock_config.get("symbol")
    timeframe = bot_mock_config.get("timeframe")

    if exchange_id and symbol and timeframe:
        # Formato sugerido: candles:exchange:symbol:timeframe
        market_topic = f"candles:{exchange_id}:{symbol}:{timeframe}"
        logger.info(f"Suscribiendo socket a stream de mercado: {market_topic}")
        await socket_manager.subscribe_to_topic(websocket, topic=market_topic)

async def handle_bot_unsubscription(websocket: WebSocket, bot_id: str):
    logger.info(f"Cliente desuscribiéndose del bot {bot_id}")
    await socket_manager.unsubscribe_from_topic(websocket, topic=f"bot:{bot_id}")
    # Nota: La desuscripción de velas puede ser compleja si el usuario tiene múltiples bots 
    # viendo el mismo mercado. Idealmente, el SocketService maneja contadores de referencia.
