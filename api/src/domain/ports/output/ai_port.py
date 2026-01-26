from abc import ABC, abstractmethod
from typing import List, Dict, Any
from api.src.domain.models.signal import SignalAnalysis

class AIPort(ABC):
    @abstractmethod
    async def analyze_signal(self, text: str, config: Dict[str, Any]) -> List[SignalAnalysis]:
        pass
