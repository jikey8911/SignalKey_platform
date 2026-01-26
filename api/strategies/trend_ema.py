import pandas as pd
from api.utils.indicators import ema
from .base import BaseStrategy

class TrendEMA(BaseStrategy):
    def __init__(self, fast=20, slow=50):
        super().__init__("TrendEMA", "Seguimiento de tendencia por cruce de EMAs")
        self.fast = fast
        self.slow = slow

    def get_signal(self, data: pd.DataFrame) -> dict:
        ema_f = ema(data['close'], period=self.fast)
        ema_s = ema(data['close'], period=self.slow)
        
        signal = 'hold'
        if ema_f.iloc[-1] > ema_s.iloc[-1] and ema_f.iloc[-2] <= ema_s.iloc[-2]:
            signal = 'buy'
        elif ema_f.iloc[-1] < ema_s.iloc[-1] and ema_f.iloc[-2] >= ema_s.iloc[-2]:
            signal = 'sell'
            
        return {'signal': signal, 'confidence': 0.75, 'ema_diff': ema_f.iloc[-1] - ema_s.iloc[-1]}