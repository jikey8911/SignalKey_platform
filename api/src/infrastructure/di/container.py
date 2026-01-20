from api.src.infrastructure.adapters.persistence.mongodb_signal_repository import MongoDBSignalRepository
from api.src.infrastructure.adapters.ai.ai_adapter import AIAdapter
from api.src.application.use_cases.process_signal import ProcessSignalUseCase
from api.models.mongodb import db
from api.services.ai_service import AIService
from api.services.socket_service import socket_service
from api.src.domain.services.notification_port import INotificationPort
from typing import Any

class SocketNotificationAdapter(INotificationPort):
    async def emit_to_user(self, user_id: str, event: str, data: Any) -> None:
        await socket_service.emit_to_user(user_id, event, data)

class Container:
    def __init__(self):
        # 1. Infraestructura / Adapters
        self.signal_repository = MongoDBSignalRepository(db)
        self.ai_service_internal = AIService()
        self.ai_adapter = AIAdapter(self.ai_service_internal)
        self.notification_adapter = SocketNotificationAdapter()
        
        # Necesitamos el bot_service que se define en main.py originalmente
        # Lo inyectaremos después o lo importaremos si es seguro
        self.bot_service = None 

    def get_process_signal_use_case(self) -> ProcessSignalUseCase:
        from api.main import signal_bot_service # Importación tardía para evitar ciclos
        return ProcessSignalUseCase(
            signal_repository=self.signal_repository,
            ai_service=self.ai_adapter,
            notification_service=self.notification_adapter,
            bot_service=signal_bot_service
        )

# Instancia global del contenedor
container = Container()
