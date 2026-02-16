import pandas as pd
from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any

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

    def on_price_tick(
        self,
        price: float,
        current_position: Optional[dict] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> int:
        """
        Hook opcional para reacción intravela (tick-by-tick).

        Contrato:
        - Debe retornar SIGNAL_WAIT | SIGNAL_BUY | SIGNAL_SELL
        - Debe ser liviano (sin recálculo pesado de indicadores)

        Implementación base: detector de spike porcentual configurable.
        Útil como fallback para estrategias que aún no implementan lógica intravela.
        """
        try:
            if price is None or price <= 0:
                return self.SIGNAL_WAIT

            ctx = context or {}
            prev_price = float(ctx.get("prev_price") or 0)
            if prev_price <= 0:
                return self.SIGNAL_WAIT

            spike_pct = float(self.config.get("tick_spike_pct", 0.8)) / 100.0
            change = (float(price) - prev_price) / prev_price

            # Si ya hay posición abierta, no forzamos nueva entrada aquí.
            if current_position and float(current_position.get("qty", 0) or 0) > 0:
                return self.SIGNAL_WAIT

            if change >= spike_pct:
                return self.SIGNAL_BUY
            if change <= -spike_pct:
                return self.SIGNAL_SELL
        except Exception:
            return self.SIGNAL_WAIT

        return self.SIGNAL_WAIT

    @abstractmethod
    def get_features(self) -> List[str]:
        """
        Retorna la lista exacta de columnas (features) que el modelo de IA 
        debe usar como entrada para predecir la señal estándar.
        """
        pass