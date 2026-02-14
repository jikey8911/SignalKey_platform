from api.src.adapters.driven.persistence.mongodb_signal_repository import MongoDBSignalRepository
from api.src.adapters.driven.persistence.telegram_repository_adapter import MongoTelegramSignalRepository, MongoTelegramTradeRepository, MongoTelegramPositionRepository
from api.src.infrastructure.adapters.ai.ai_adapter import AIAdapter
from api.src.adapters.driven.exchange.cex_adapter import CEXAdapter
from api.src.application.use_cases.process_signal import ProcessSignalUseCase
from api.src.adapters.driven.persistence.mongodb import db
from api.src.application.services.ai_service import AIService
from api.src.adapters.driven.notifications.socket_service import socket_service
from api.src.domain.ports.output.notification_port import INotificationPort
from api.src.adapters.driven.exchange.stream_service import MarketStreamService
from api.src.application.services.price_alert_manager import PriceAlertManager
from typing import Any

class SocketNotificationAdapter(INotificationPort):
    async def emit_to_user(self, user_id: str, event: str, data: Any) -> None:
        await socket_service.emit_to_user(user_id, event, data)

class Container:
    def __init__(self):
        # 1. Infraestructura / Adapters
        self.signal_repository = MongoDBSignalRepository(db)
        self.telegram_signal_repository = MongoTelegramSignalRepository()
        self.telegram_trade_repository = MongoTelegramTradeRepository()
        self.telegram_position_repository = MongoTelegramPositionRepository()
        
        self.ai_service_internal = AIService()
        self.ai_adapter = AIAdapter(self.ai_service_internal)
        self.cex_adapter = CEXAdapter() 
        self.notification_adapter = SocketNotificationAdapter()
        
        # 2. Servicios de Aplicación Base
        self.stream_service = MarketStreamService()
        self.price_alert_manager = PriceAlertManager(self.stream_service)
        
        # El bot_service (SignalBotService) se inyecta dinámicamente desde api.main

    def get_process_signal_use_case(self) -> ProcessSignalUseCase:
        from api.main import telegram_trade_service # Importación tardía para evitar ciclos
        return ProcessSignalUseCase(
            signal_repository=self.signal_repository,
            ai_service=self.ai_adapter,
            notification_service=self.notification_adapter,
            telegram_signal_repository=self.telegram_signal_repository,
            telegram_trade_repository=self.telegram_trade_repository,
            trade_service=telegram_trade_service
        )

# Instancia global del contenedor
container = Container()
