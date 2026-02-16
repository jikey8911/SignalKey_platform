import numpy as np
import pandas as pd
from typing import List
from api.src.domain.strategies.base import BaseStrategy

class GoldenCrossStrategy(BaseStrategy):
    """
    Clásica estrategia de tendencia.
    Compra: SMA rápida cruza arriba de SMA lenta.
    Venta: SMA rápida cruza debajo de SMA lenta.
    """
    def apply(self, df: pd.DataFrame, current_position: dict = None) -> pd.DataFrame:
        short_window = self.config.get('short_window', 50)
        long_window = self.config.get('long_window', 200)

        df['sma_fast'] = df['close'].rolling(window=short_window).mean()
        df['sma_slow'] = df['close'].rolling(window=long_window).mean()

        df['signal'] = self.SIGNAL_WAIT
        
        # Señal de Compra (Cruce alcista)
        buy_cond = (df['sma_fast'] > df['sma_slow']) & (df['sma_fast'].shift(1) <= df['sma_slow'].shift(1))
        df.loc[buy_cond, 'signal'] = self.SIGNAL_BUY

        # Señal de Venta (Cruce bajista)
        sell_cond = (df['sma_fast'] < df['sma_slow']) & (df['sma_fast'].shift(1) >= df['sma_slow'].shift(1))
        df.loc[sell_cond, 'signal'] = self.SIGNAL_SELL

        return df

    def on_price_tick(self, price: float, current_position: dict = None, context: dict = None) -> int:
        """Tick intravela liviano (fallback): delega al BaseStrategy."""
        return super().on_price_tick(price, current_position=current_position, context=context)


    def get_features(self) -> List[str]:
        return ['sma_fast', 'sma_slow']
