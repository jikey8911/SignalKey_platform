from abc import ABC, abstractmethod
from typing import List
from api.core.domain.signal import RawSignal, SignalAnalysis

class AIPort(ABC):
    @abstractmethod
    async def analyze_signal(self, signal: RawSignal, config: dict = None) -> List[SignalAnalysis]:
        pass
