from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from src.adapters.driven.notifications.socket_service import socket_service
import logging

logger = logging.getLogger(__name__)

router = APIRouter(tags=["websocket"])

@router.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str):
    logger.info(f"New WebSocket connection request from user: {user_id}")
    try:
        await socket_service.connect(websocket, user_id)
        while True:
            # Mantener conexión viva y escuchar mensajes si es necesario
            # Por ahora el cliente solo recibe, pero debemos esperar para no cerrar
            data = await websocket.receive_text()
            # Posiblemente manejar "ping" o comandos simples
            if data == "ping":
                await websocket.send_text("pong")
                
    except WebSocketDisconnect:
        socket_service.disconnect(websocket, user_id)
    except Exception as e:
        logger.error(f"WebSocket error for user {user_id}: {e}")
        socket_service.disconnect(websocket, user_id)
