from abc import ABC, abstractmethod
from typing import List, Optional
from api.src.domain.entities.signal import Signal

class ISignalRepository(ABC):
    @abstractmethod
    async def save(self, signal: Signal) -> Signal:
        pass

    @abstractmethod
    async def update(self, signal_id: str, update_data: dict) -> bool:
        pass

    @abstractmethod
    async def find_by_id(self, signal_id: str) -> Optional[Signal]:
        pass

    @abstractmethod
    async def find_by_user(self, user_id: str) -> List[Signal]:
        pass
