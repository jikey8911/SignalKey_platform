import pandas as pd
from api.utils.indicators import donchian
from .base import BaseStrategy

class VolatilityBreakout(BaseStrategy):
    def __init__(self, period=20):
        super().__init__("VolatilityBreakout", "Ruptura de canales de precio con alta volatilidad")
        self.period = period

    def get_signal(self, data: pd.DataFrame) -> dict:
        dc = donchian(data['high'], data['low'], period=self.period)
        upper_band = dc['upper'] # Banda superior
        
        current_close = data['close'].iloc[-1]
        
        signal = 'hold'
        if current_close > upper_band.iloc[-2]:
            signal = 'buy'
        
        return {'signal': signal, 'confidence': 0.85, 'breakout_level': upper_band.iloc[-2]}