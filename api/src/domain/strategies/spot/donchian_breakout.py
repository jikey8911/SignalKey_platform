import numpy as np
import pandas as pd
from typing import List
from api.src.domain.strategies.base import BaseStrategy

class DonchianBreakoutStrategy(BaseStrategy):
    """
    Compra cuando el precio supera el máximo de N periodos (Ruptura).
    """
    def apply(self, df: pd.DataFrame, current_position: dict = None) -> pd.DataFrame:
        window = self.config.get('window', 20)
        
        df['donchian_high'] = df['high'].rolling(window=window).max().shift(1) # Shift para evitar look-ahead bias
        df['donchian_low'] = df['low'].rolling(window=window).min().shift(1)

        df['signal'] = self.SIGNAL_WAIT
        
        # Breakout Alcista
        df.loc[df['close'] > df['donchian_high'], 'signal'] = self.SIGNAL_BUY
        
        # Breakout Bajista (Exit para spot)
        df.loc[df['close'] < df['donchian_low'], 'signal'] = self.SIGNAL_SELL

        return df

    def get_features(self) -> List[str]:
        return ['donchian_high', 'donchian_low']
