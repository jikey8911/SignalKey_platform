from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from datetime import datetime

class ITelegramSignalRepository(ABC):
    @abstractmethod
    async def save_signal(self, signal_data: Dict[str, Any]) -> str:
        """Guarda una señal (aprobada o rechazada) para auditoría/estadísticas."""
        pass

class ITelegramTradeRepository(ABC):
    @abstractmethod
    async def create_trade(self, trade_data: Dict[str, Any]) -> str:
        """Crea un nuevo registro de trade de Telegram."""
        pass

    @abstractmethod
    async def update_trade(self, trade_id: str, updates: Dict[str, Any]):
        """Actualiza un trade existente."""
        pass

    @abstractmethod
    async def get_active_trades(self, exchange_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Obtiene trades en estado waiting_entry o active."""
        pass

    @abstractmethod
    async def has_active_trade(self, user_id: str, symbol: str) -> bool:
        """Verifica si ya existe una operación abierta o esperando para ese par."""
        pass

class ITelegramPositionRepository(ABC):
    @abstractmethod
    async def upsert_position(self, trade_id: str, position_data: Dict[str, Any]):
        """Crea o actualiza la posición en vivo (Live)."""
        pass

    @abstractmethod
    async def close_position(self, trade_id: str):
        """Marca la posición como cerrada o la elimina de la tabla de posiciones activas."""
        pass
