from abc import ABC, abstractmethod
from typing import List, Optional
from api.src.domain.entities.bot_instance import BotInstance

class IBotRepository(ABC):
    @abstractmethod
    async def get_active_bots(self) -> List[BotInstance]:
        """Obtiene todos los bots con estado 'running'."""
        pass

    @abstractmethod
    async def get_bot(self, bot_id: str) -> Optional[BotInstance]:
        """Obtiene un bot específico por su ID."""
        pass

    @abstractmethod
    async def save(self, bot: BotInstance) -> BotInstance:
        """Guarda o actualiza un bot."""
        pass