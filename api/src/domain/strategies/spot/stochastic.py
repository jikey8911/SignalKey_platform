import numpy as np
import pandas as pd
from typing import List
from api.src.domain.strategies.base import BaseStrategy

class StochasticStrategy(BaseStrategy):
    """
    Identifica puntos de giro.
    Compra: %K cruza por encima de %D en zona baja (<20).
    """
    def apply(self, df: pd.DataFrame, current_position: dict = None) -> pd.DataFrame:
        k_period = self.config.get('k_period', 14)
        d_period = self.config.get('d_period', 3)
        
        low_min = df['low'].rolling(window=k_period).min()
        high_max = df['high'].rolling(window=k_period).max()
        
        df['stoch_k'] = 100 * ((df['close'] - low_min) / (high_max - low_min))
        df['stoch_d'] = df['stoch_k'].rolling(window=d_period).mean()

        df['signal'] = self.SIGNAL_WAIT
        
        # Cruce alcista en sobreventa
        buy_cond = (df['stoch_k'] > df['stoch_d']) & (df['stoch_k'] < 20) & (df['stoch_k'].shift(1) <= df['stoch_d'].shift(1))
        df.loc[buy_cond, 'signal'] = self.SIGNAL_BUY

        # Cruce bajista en sobrecompra
        sell_cond = (df['stoch_k'] < df['stoch_d']) & (df['stoch_k'] > 80)
        df.loc[sell_cond, 'signal'] = self.SIGNAL_SELL

        return df

    def on_price_tick(self, price: float, current_position: dict = None, context: dict = None) -> int:
        """Tick intravela liviano (fallback): delega al BaseStrategy."""
        return super().on_price_tick(price, current_position=current_position, context=context)


    def get_features(self) -> List[str]:
        return ['stoch_k', 'stoch_d']
