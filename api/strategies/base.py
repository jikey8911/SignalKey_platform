from abc import ABC, abstractmethod
import pandas as pd
from typing import Dict, Any, Optional

class BaseStrategy(ABC):
    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description

    @abstractmethod
    def get_signal(self, data: pd.DataFrame, position_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Analiza los datos y retorna una señal considerando el estado de la posición actual.
        
        Args:
            data (pd.DataFrame): DataFrame con al menos columnas 'open', 'high', 'low', 'close', 'volume'.
            position_context (Optional[Dict]): Información de posición actual:
                - has_position: bool
                - position_type: 'LONG' | 'SHORT' | None
                - avg_entry_price: float
                - current_price: float
                - unrealized_pnl_pct: float
                - position_count: int
            
        Returns:
            dict: {
                'signal': 'buy' | 'sell' | 'hold',
                'confidence': float (0.0 to 1.0),
                'meta': dict (extra info, optional)
            }
        """
        pass
