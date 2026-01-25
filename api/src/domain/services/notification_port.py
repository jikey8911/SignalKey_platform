from abc import ABC, abstractmethod
from typing import Any

class INotificationPort(ABC):
    @abstractmethod
    async def emit_to_user(self, user_id: str, event: str, data: Any) -> None:
        pass
