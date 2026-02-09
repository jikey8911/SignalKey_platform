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

# Instancias globales
from api.src.adapters.driven.notifications.socket_service import socket_service
from api.src.adapters.driven.persistence.mongodb_bot_repository import MongoBotRepository
from api.src.adapters.driven.persistence.mongodb_signal_repository import MongoDBSignalRepository
from api.src.adapters.driven.persistence.mongodb import db

bot_repo = MongoBotRepository()
signal_repo = MongoDBSignalRepository(db)

@router.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str):
    await socket_service.connect(websocket, user_id)
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
        socket_service.disconnect(websocket, user_id)
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
    
    # A) OBTENER DATOS REALES
    bot_doc = await bot_repo.collection.find_one({"_id": ObjectId(bot_id)})
    if not bot_doc:
        logger.warning(f"Suspensión fallida: Bot {bot_id} no encontrado.")
        return

    # Mapear para el frontend
    bot_id_str = str(bot_doc["_id"])
    symbol = bot_doc.get("symbol", "BTC/USDT")
    timeframe = bot_doc.get("timeframe", "1h")
    exchange_id = (bot_doc.get("exchangeId") or bot_doc.get("exchange_id") or "binance").lower()

    # Obtener señales recientes
    signals = await signal_repo.find_by_bot_id(bot_id)
    
    # Obtener posición activa
    active_position = await db["positions"].find_one({
        "botId": bot_doc["_id"],
        "status": "OPEN"
    })

    snapshot_data = {
        "type": "bot_snapshot",
        "bot_id": bot_id_str,
        "config": {
            "id": bot_id_str,
            "name": bot_doc.get("name"),
            "symbol": symbol,
            "timeframe": timeframe,
            "exchange_id": exchange_id,
            "status": bot_doc.get("status")
        },
        "positions": [_serialize_mongo(active_position)] if active_position else [],
        "signals": [s.to_dict() for s in signals]
    }
    
    # B) ENVIAR SNAPSHOT
    await websocket.send_json(snapshot_data)
    
    # C) GESTIONAR SUSCRIPCIÓN EN EL SOCKET MANAGER
    await socket_service.subscribe_to_topic(websocket, topic=f"bot:{bot_id}")
    
    # D) SUSCRIBIR A VELAS
    market_topic = f"candles:{exchange_id}:{symbol}:{timeframe}"
    logger.info(f"Suscribiendo socket a stream de mercado: {market_topic}")
    await socket_service.subscribe_to_topic(websocket, topic=market_topic)

async def handle_bot_unsubscription(websocket: WebSocket, bot_id: str):
    logger.info(f"Cliente desuscribiéndose del bot {bot_id}")
    await socket_service.unsubscribe_from_topic(websocket, topic=f"bot:{bot_id}")
    # Nota: También deberíamos desuscribir de las velas, pero esto requiere 
    # saber qué velas estaba viendo este bot.
    # Por ahora simplificado.

def _serialize_mongo(obj):
    from bson import ObjectId
    if isinstance(obj, list): return [_serialize_mongo(i) for i in obj]
    if isinstance(obj, dict): return {k: _serialize_mongo(v) for k, v in obj.items()}
    if isinstance(obj, ObjectId): return str(obj)
    return obj

from bson import ObjectId
