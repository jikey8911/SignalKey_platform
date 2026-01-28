import pandas as pd
from api.utils.indicators import donchian
from .base import BaseStrategy

class VolatilityBreakout(BaseStrategy):
    def __init__(self, period=20):
        super().__init__("VolatilityBreakout", "Ruptura de canales arriba/abajo")
        self.period = period

    def get_signal(self, data: pd.DataFrame, position_context: dict = None) -> dict:
        dc = donchian(data['high'], data['low'], period=self.period)
        pos = position_context or {'has_position': False}
        
        current_close = data['close'].iloc[-1]
        upper = dc['upper'].iloc[-2]
        lower = dc['lower'].iloc[-2]  # Añadida lógica para cortos
        
        signal = 'hold'
        if current_close > upper:
            signal = 'buy'  # Ruptura alcista (Pyramiding allowed)
        elif current_close < lower:
            signal = 'sell'  # Ruptura bajista (Pyramiding allowed)
            
        return {'signal': signal, 'confidence': 0.85}