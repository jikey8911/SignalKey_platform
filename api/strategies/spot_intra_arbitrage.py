import pandas as pd
from .base import BaseStrategy

class SpotIntraExchangeArbitrage(BaseStrategy):
    def __init__(self, period=20, z_threshold=2.0, min_profit=0.5):
        super().__init__("Spot_Arbitrage", "Arbitraje estadístico bidireccional")
        self.period = period
        self.z_threshold = z_threshold
        self.min_profit = min_profit

    def get_signal(self, data: pd.DataFrame, position_context: dict = None) -> dict:
        close = data['close']
        avg = close.rolling(self.period).mean().iloc[-1]
        std = close.rolling(self.period).std().iloc[-1]
        z_score = (close.iloc[-1] - avg) / std if std != 0 else 0
        
        pos = position_context or {'has_position': False}
        pnl = pos.get('unrealized_pnl_pct', 0)
        signal = 'hold'

        # Lógica para abrir/promediar (Sin restricción de PnL)
        if z_score <= -self.z_threshold:  # Infravalorado
             signal = 'buy'
        elif z_score >= self.z_threshold:  # Sobrevalorado
             signal = 'sell'

        # Lógica para cerrar con profit
        if pos.get('has_position') and pnl >= self.min_profit:
            if pos.get('position_type') == 'LONG' and z_score >= 0:
                signal = 'sell'
            if pos.get('position_type') == 'SHORT' and z_score <= 0:
                signal = 'buy'

        return {'signal': signal, 'confidence': 0.9, 'meta': {'z_score': z_score, 'pnl': pnl}}
