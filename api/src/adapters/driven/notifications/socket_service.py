import json
import logging
from typing import Dict, List, Any
from fastapi import WebSocket

logger = logging.getLogger(__name__)

class SocketService:
    def __init__(self):
        # user_id -> list of active WebSocket connections
        self.active_connections: Dict[str, List[WebSocket]] = {}
        # topic -> set of WebSocket connections
        self.topic_subscriptions: Dict[str, set[WebSocket]] = {}

    def is_user_connected(self, user_id: str) -> bool:
        return bool(self.active_connections.get(user_id))

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
        
        # Remove from all topics
        for topic in list(self.topic_subscriptions.keys()):
            if websocket in self.topic_subscriptions[topic]:
                self.topic_subscriptions[topic].remove(websocket)
                if not self.topic_subscriptions[topic]:
                    del self.topic_subscriptions[topic]

    async def subscribe_to_topic(self, websocket: WebSocket, topic: str):
        if topic not in self.topic_subscriptions:
            self.topic_subscriptions[topic] = set()
        self.topic_subscriptions[topic].add(websocket)
        logger.info(f"Socket subscribed to topic: {topic}")

    async def unsubscribe_from_topic(self, websocket: WebSocket, topic: str):
        if topic in self.topic_subscriptions:
            if websocket in self.topic_subscriptions[topic]:
                self.topic_subscriptions[topic].remove(websocket)
                if not self.topic_subscriptions[topic]:
                    del self.topic_subscriptions[topic]
        logger.info(f"Socket unsubscribed from topic: {topic}")

    async def emit_to_topic(self, topic: str, event: str, data: Any):
        websockets = self.topic_subscriptions.get(topic, set())
        if not websockets:
            return

        message = json.dumps({
            "event": event,
            "data": data
        }, default=str)

        for ws in list(websockets):
            try:
                await ws.send_text(message)
            except Exception as e:
                logger.error(f"Error emitting to topic {topic}: {e}")
                # We don't have user_id here easily, so we just remove from topic
                if ws in self.topic_subscriptions[topic]:
                    self.topic_subscriptions[topic].remove(ws)

    async def emit_to_user(self, user_id: str, event: str, data: Any):
        """Envía un evento a todas las conexiones activas del usuario"""
        websockets = self.active_connections.get(user_id, [])
        if not websockets:
            return

        message = json.dumps({
            "event": event,
            "data": data
        }, default=str)

        # Iterate over a copy to avoid issues during modification
        for ws in list(websockets):
            try:
                await ws.send_text(message)
            except Exception as e:
                logger.error(f"Error emitting to user {user_id} on a specific socket: {e}")
                self.disconnect(ws, user_id)

    async def broadcast(self, event: str, data: Any):
        """Envía un evento a todos los usuarios conectados"""
        for user_id in list(self.active_connections.keys()):
            await self.emit_to_user(user_id, event, data)

socket_service = SocketService()
