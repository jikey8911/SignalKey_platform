import pandas as pd
from api.utils.indicators import rsi
from .base import BaseStrategy

class RSIReversion(BaseStrategy):
    def __init__(self, period=14, overbought=70, oversold=30):
        super().__init__("RSIReversion", "Compra en sobreventa y vende en sobrecompra")
        self.period = period
        self.overbought = overbought
        self.oversold = oversold

    def get_signal(self, data: pd.DataFrame) -> dict:
        rsi_val = rsi(data['close'], period=self.period)
        last_rsi = rsi_val.iloc[-1]
        
        signal = 'hold'
        if last_rsi < self.oversold:
            signal = 'buy'
        elif last_rsi > self.overbought:
            signal = 'sell'
            
        return {'signal': signal, 'confidence': 0.8, 'indicator_value': last_rsi}