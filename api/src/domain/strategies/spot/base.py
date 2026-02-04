import pandas as pd
from abc import ABC, abstractmethod
from typing import List

class BaseStrategy(ABC):
    """
    Clase base que define el contrato estándar para todas las estrategias.
    Garantiza que la IA aprenda de columnas dinámicas pero responda señales universales.
    """
    
    # --- CONTRATO DE SEÑALES ESTÁNDAR (Inamovible para el Motor) ---
    SIGNAL_WAIT = 0   # Neutro / Esperar
    SIGNAL_BUY = 1    # LONG / Compra
    SIGNAL_SELL = 2   # SHORT / Venta

    def __init__(self, config: dict = None):
        self.config = config or {}
        self.name = self.__class__.__name__

    @abstractmethod
    def apply(self, df: pd.DataFrame, current_position: dict = None) -> pd.DataFrame:
        """
        Calcula indicadores y genera la columna 'signal' 
        usando exclusivamente las constantes SIGNAL_*.
        Ahora recibe 'current_position' opcional para lógica dependiente del estado.
        """
        pass

    @abstractmethod
    def get_features(self) -> List[str]:
        """
        Retorna la lista exacta de columnas (features) que el modelo de IA 
        debe usar como entrada para predecir la señal estándar.
        """
        pass