from abc import ABC, abstractmethod
from typing import List, Optional
# Ajustamos el import para seguir la convención 'api.src...'
from api.src.domain.entities.signal import Signal

class ISignalRepository(ABC):
    @abstractmethod
    async def save(self, signal: Signal) -> Signal:
        """Guarda una nueva señal."""
        pass

    @abstractmethod
    async def get_recent_by_bot(self, bot_id: str, limit: int = 50) -> List[Signal]:
        """Obtiene las señales más recientes generadas por un bot."""
        pass