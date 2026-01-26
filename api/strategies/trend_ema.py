import pandas as pd
from api.utils.indicators import ema
from .base import BaseStrategy

class TrendEMA(BaseStrategy):
    def __init__(self, fast=20, slow=50):
        super().__init__("TrendEMA", "Seguimiento de tendencia bidireccional")
        self.fast = fast
        self.slow = slow

    def get_signal(self, data: pd.DataFrame, position_context: dict = None) -> dict:
        f_ema = ema(data['close'], self.fast)
        s_ema = ema(data['close'], self.slow)
        pos = position_context or {'has_position': False}
        
        signal = 'hold'
        # Cruce Dorado (Long)
        if f_ema.iloc[-1] > s_ema.iloc[-1] and f_ema.iloc[-2] <= s_ema.iloc[-2]:
            signal = 'buy'
        # Cruce de la Muerte (Short)
        elif f_ema.iloc[-1] < s_ema.iloc[-1] and f_ema.iloc[-2] >= s_ema.iloc[-2]:
            signal = 'sell'
            
        return {'signal': signal, 'confidence': 0.75}