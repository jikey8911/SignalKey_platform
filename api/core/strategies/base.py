from abc import ABC, abstractmethod
from typing import List, Dict, Any

class BaseStrategy(ABC):
    """
    Abstract base class for AI Trading Strategies.
    Defines how an AI model should behave, what it looks for, 
    and how strict it should be.
    """
    
    @property
    @abstractmethod
    def name(self) -> str:
        pass
        
    @property
    @abstractmethod
    def description(self) -> str:
        pass

    @abstractmethod
    def build_prompt(self, recent_candles: List[dict], current_price: float) -> str:
        """
        Builds the specific prompt for the AI based on this strategy's logic.
        """
        pass
