import numpy as np
import pandas as pd
from typing import List
from api.src.domain.strategies.base import BaseStrategy

class OBVStrategy(BaseStrategy):
    """
    Usa el flujo de volumen para confirmar tendencias.
    Compra: El OBV rompe su media móvil hacia arriba.
    """
    def apply(self, df: pd.DataFrame, current_position: dict = None) -> pd.DataFrame:
        # Cálculo OBV
        df['obv'] = (np.sign(df['close'].diff()) * df['volume']).fillna(0).cumsum()
        df['obv_ma'] = df['obv'].rolling(window=20).mean()

        df['signal'] = self.SIGNAL_WAIT

        # OBV cruza su media hacia arriba
        buy_cond = (df['obv'] > df['obv_ma']) & (df['obv'].shift(1) <= df['obv_ma'].shift(1))
        df.loc[buy_cond, 'signal'] = self.SIGNAL_BUY
        
        # OBV cruza su media hacia abajo
        sell_cond = (df['obv'] < df['obv_ma']) & (df['obv'].shift(1) >= df['obv_ma'].shift(1))
        df.loc[sell_cond, 'signal'] = self.SIGNAL_SELL

        return df

    def get_features(self) -> List[str]:
        return ['obv', 'obv_ma']
