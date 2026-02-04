import numpy as np
import pandas as pd
from typing import List
from api.src.domain.strategies.base import BaseStrategy

class MomentumStrategy(BaseStrategy):
    """
    Mide la velocidad del cambio de precio.
    Compra: Momentum cruza de negativo a positivo (aceleración).
    """
    def apply(self, df: pd.DataFrame, current_position: dict = None) -> pd.DataFrame:
        n = self.config.get('period', 10)
        
        # Rate of Change: ((Precio actual / Precio hace n periodos) - 1) * 100
        df['roc'] = ((df['close'] / df['close'].shift(n)) - 1) * 100

        df['signal'] = self.SIGNAL_WAIT

        # Cruce de línea cero
        buy_cond = (df['roc'] > 0) & (df['roc'].shift(1) <= 0)
        sell_cond = (df['roc'] < 0) & (df['roc'].shift(1) >= 0)

        df.loc[buy_cond, 'signal'] = self.SIGNAL_BUY
        df.loc[sell_cond, 'signal'] = self.SIGNAL_SELL

        return df

    def get_features(self) -> List[str]:
        return ['roc']
