from abc import ABC, abstractmethod
from typing import List, Dict, Any
from api.src.domain.entities.signal import SignalAnalysis

class IAIPort(ABC):
    @abstractmethod
    async def analyze_signal(self, text: str, config: Dict[str, Any]) -> List[SignalAnalysis]:
        pass
