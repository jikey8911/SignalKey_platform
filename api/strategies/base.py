from abc import ABC, abstractmethod
import pandas as pd
from typing import Dict, Any

class BaseStrategy(ABC):
    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description

    @abstractmethod
    def get_signal(self, data: pd.DataFrame) -> Dict[str, Any]:
        """
        Analiza los datos y retorna una señal.
        
        Args:
            data (pd.DataFrame): DataFrame con al menos columnas 'open', 'high', 'low', 'close', 'volume'.
            
        Returns:
            dict: {
                'signal': 'buy' | 'sell' | 'hold',
                'confidence': float (0.0 to 1.0),
                'meta': dict (extra info)
            }
        """
        pass
