import numpy as np
import pandas as pd
from typing import List
from api.src.domain.strategies.base import BaseStrategy

class RSIStrategy(BaseStrategy):
    """
    Compra en sobreventa (<30) y Vende en sobrecompra (>70).
    Ideal para mercados laterales en Spot.
    """
    def apply(self, df: pd.DataFrame, current_position: dict = None) -> pd.DataFrame:
        period = self.config.get('period', 14)
        lower_bound = self.config.get('lower', 30)
        upper_bound = self.config.get('upper', 70)

        # Cálculo manual de RSI vectorizado
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))

        df['signal'] = self.SIGNAL_WAIT
        
        # Compra al salir de sobreventa hacia arriba
        df.loc[(df['rsi'] < lower_bound), 'signal'] = self.SIGNAL_BUY
        
        # Venta al entrar en sobrecompra
        df.loc[(df['rsi'] > upper_bound), 'signal'] = self.SIGNAL_SELL

        return df

    def get_features(self) -> List[str]:
        return ['rsi']
