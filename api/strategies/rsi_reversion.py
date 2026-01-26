import pandas as pd
from api.utils.indicators import rsi
from .base import BaseStrategy

class RSIReversion(BaseStrategy):
    def __init__(self, period=14, overbought=70, oversold=30, min_profit=0.5):
        super().__init__("RSIReversion", "Reversión en extremos con profit aware")
        self.period = period
        self.overbought = overbought
        self.oversold = oversold
        self.min_profit = min_profit

    def get_signal(self, data: pd.DataFrame, position_context: dict = None) -> dict:
        last_rsi = rsi(data['close'], period=self.period).iloc[-1]
        pos = position_context or {'has_position': False}
        pnl = pos.get('unrealized_pnl_pct', 0)
        
        signal = 'hold'
        # Entradas
        if last_rsi < self.oversold and not pos['has_position']:
            signal = 'buy'
        elif last_rsi > self.overbought and not pos['has_position']:
            signal = 'sell'
        
        # Salidas controladas
        if pos.get('has_position') and pnl >= self.min_profit:
            if pos.get('position_type') == 'LONG' and last_rsi > 50:
                signal = 'sell'
            if pos.get('position_type') == 'SHORT' and last_rsi < 50:
                signal = 'buy'
            
        return {'signal': signal, 'confidence': 0.8, 'meta': {'rsi': last_rsi, 'pnl': pnl}}