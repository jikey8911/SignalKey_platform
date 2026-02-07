from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from api.src.adapters.driven.notifications.socket_service import socket_service
import logging
import json
from bson import ObjectId
from api.src.adapters.driven.persistence.mongodb_bot_repository import MongoBotRepository
from api.src.adapters.driven.persistence.mongodb import db

logger = logging.getLogger(__name__)

router = APIRouter(tags=["websocket"])

repo = MongoBotRepository()

def _serialize_mongo(obj):
    """
    Recursively convert ObjectId to string to make data JSON serializable.
    """
    if isinstance(obj, list):
        return [_serialize_mongo(i) for i in obj]
    if isinstance(obj, dict):
        return {k: _serialize_mongo(v) for k, v in obj.items()}
    if isinstance(obj, ObjectId):
        return str(obj)
    return obj

@router.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str):
    logger.info(f"New WebSocket connection request from user: {user_id}")
    try:
        await socket_service.connect(websocket, user_id)
        while True:
            # Mantener conexión viva y escuchar mensajes
            data_text = await websocket.receive_text()

            try:
                # Intentar parsear como JSON
                message = json.loads(data_text)

                if isinstance(message, dict) and message.get("action") == "get_bots":
                    # Recuperar bots del usuario
                    bots = await repo.get_all_by_user(user_id)
                    result = []

                    for bot in bots:
                        b_dict = bot.to_dict()

                        # Enrich with active trade data if exists
                        active_trade = await db.trades.find_one({
                            "userId": user_id,
                            "symbol": bot.symbol,
                            "status": "active"
                        })

                        if active_trade:
                            b_dict["active_trade_id"] = str(active_trade["_id"])
                            b_dict["pnl"] = active_trade.get("pnl", 0.0)
                            b_dict["current_price"] = active_trade.get("currentPrice", 0.0)
                            b_dict["status"] = "active" # Force active status if trade is running
                        else:
                            b_dict["active_trade_id"] = None
                            b_dict["pnl"] = 0.0
                            b_dict["current_price"] = 0.0

                        result.append(b_dict)

                    # Enviar respuesta serializada
                    serialized_result = _serialize_mongo(result)
                    await socket_service.emit_to_user(user_id, "all_bots_list", serialized_result)

            except json.JSONDecodeError:
                # Mantener compatibilidad con mensajes de texto simple como "ping"
                if data_text == "ping":
                    await websocket.send_text("pong")
                
    except WebSocketDisconnect:
        socket_service.disconnect(websocket, user_id)
    except Exception as e:
        logger.error(f"WebSocket error for user {user_id}: {e}")
        socket_service.disconnect(websocket, user_id)
