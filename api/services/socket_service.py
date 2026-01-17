import json
import logging
from typing import Dict, List, Any
from fastapi import WebSocket

logger = logging.getLogger(__name__)

class SocketService:
    def __init__(self):
        # user_id -> list of active WebSocket connections
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, user_id: str):
        await websocket.accept()
        if user_id not in self.active_connections:
            self.active_connections[user_id] = []
        self.active_connections[user_id].append(websocket)
        logger.info(f"Client connected to WebSocket: {user_id}. Total connections for user: {len(self.active_connections[user_id])}")

    def disconnect(self, websocket: WebSocket, user_id: str):
        if user_id in self.active_connections:
            if websocket in self.active_connections[user_id]:
                self.active_connections[user_id].remove(websocket)
                if not self.active_connections[user_id]:
                    del self.active_connections[user_id]
            logger.info(f"Client disconnected from WebSocket: {user_id}")

    async def emit_to_user(self, user_id: str, event: str, data: Any):
        """Envía un evento a todas las conexiones activas de un usuario"""
        if user_id not in self.active_connections:
            return

        message = json.dumps({
            "event": event,
            "data": data
        }, default=str)

        disconnected_websockets = []
        for websocket in self.active_connections[user_id]:
            try:
                await websocket.send_text(message)
            except Exception as e:
                logger.error(f"Error emitting to user {user_id}: {e}")
                disconnected_websockets.append(websocket)
        
        # Limpiar conexiones muertas
        for ws in disconnected_websockets:
            self.disconnect(ws, user_id)

    async def broadcast(self, event: str, data: Any):
        """Envía un evento a absolutamente todos los clientes conectados"""
        message = json.dumps({
            "event": event,
            "data": data
        }, default=str)
        
        for user_id in list(self.active_connections.keys()):
            await self.emit_to_user(user_id, event, data)

socket_service = SocketService()
