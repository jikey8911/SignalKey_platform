import numpy as np
import pandas as pd
from typing import List
from api.src.domain.strategies.base import BaseStrategy

class VWAPStrategy(BaseStrategy):
    """
    Volume Weighted Average Price.
    Compra: Precio cruza por encima del VWAP (Confirmación de fuerza).
    Venta: Precio cruza por debajo.
    *Requiere columna 'volume'*
    """
    def apply(self, df: pd.DataFrame, current_position: dict = None) -> pd.DataFrame:
        # Cálculo acumulativo simple (pseudo-VWAP para dataset continuo)
        # En producción real, el VWAP se reinicia cada día.
        cum_vol = df['volume'].cumsum()
        cum_vol_price = (df['close'] * df['volume']).cumsum()
        df['vwap'] = cum_vol_price / cum_vol

        df['signal'] = self.SIGNAL_WAIT
        
        buy_cond = (df['close'] > df['vwap']) & (df['close'].shift(1) <= df['vwap'].shift(1))
        sell_cond = (df['close'] < df['vwap']) & (df['close'].shift(1) >= df['vwap'].shift(1))

        df.loc[buy_cond, 'signal'] = self.SIGNAL_BUY
        df.loc[sell_cond, 'signal'] = self.SIGNAL_SELL

        return df

    def get_features(self) -> List[str]:
        return ['vwap']
