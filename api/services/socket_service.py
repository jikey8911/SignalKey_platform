import json
import logging
from typing import Dict, List, Any
from fastapi import WebSocket

logger = logging.getLogger(__name__)

class SocketService:
    def __init__(self):
        # user_id -> single active WebSocket connection
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, user_id: str):
        # Si ya existe una conexión para este usuario, la cerramos para mantener solo una
        if user_id in self.active_connections:
            old_ws = self.active_connections[user_id]
            try:
                logger.info(f"Closing existing connection for user {user_id} to prevent duplicates.")
                await old_ws.close()
            except Exception as e:
                logger.debug(f"Error closing old websocket: {e}")
        
        await websocket.accept()
        self.active_connections[user_id] = websocket
        logger.info(f"Client connected to WebSocket: {user_id}. Established single active connection.")

    def disconnect(self, websocket: WebSocket, user_id: str):
        if user_id in self.active_connections:
            if self.active_connections[user_id] == websocket:
                del self.active_connections[user_id]
                logger.info(f"Client disconnected from WebSocket: {user_id}")

    async def emit_to_user(self, user_id: str, event: str, data: Any):
        """Envía un evento a la conexión activa del usuario"""
        websocket = self.active_connections.get(user_id)
        if not websocket:
            return

        message = json.dumps({
            "event": event,
            "data": data
        }, default=str)

        try:
            await websocket.send_text(message)
        except Exception as e:
            logger.error(f"Error emitting to user {user_id}: {e}")
            self.disconnect(websocket, user_id)

    async def broadcast(self, event: str, data: Any):
        """Envía un evento a todos los usuarios conectados (una sola conexión por usuario)"""
        for user_id in list(self.active_connections.keys()):
            await self.emit_to_user(user_id, event, data)

socket_service = SocketService()
