import numpy as np
import pandas as pd
from typing import List
from api.src.domain.strategies.base import BaseStrategy

class MACDStrategy(BaseStrategy):
    """
    Sigue la inercia del precio.
    Compra: Línea MACD cruza encima de Señal.
    Venta: Línea MACD cruza debajo de Señal.
    """
    def apply(self, df: pd.DataFrame, current_position: dict = None) -> pd.DataFrame:
        fast = self.config.get('fast', 12)
        slow = self.config.get('slow', 26)
        signal_smooth = self.config.get('signal', 9)

        exp1 = df['close'].ewm(span=fast, adjust=False).mean()
        exp2 = df['close'].ewm(span=slow, adjust=False).mean()
        df['macd'] = exp1 - exp2
        df['macd_signal'] = df['macd'].ewm(span=signal_smooth, adjust=False).mean()
        df['macd_hist'] = df['macd'] - df['macd_signal']

        df['signal'] = self.SIGNAL_WAIT
        
        # Cruce alcista
        crossover = (df['macd'] > df['macd_signal']) & (df['macd'].shift(1) <= df['macd_signal'].shift(1))
        df.loc[crossover, 'signal'] = self.SIGNAL_BUY

        # Cruce bajista
        crossunder = (df['macd'] < df['macd_signal']) & (df['macd'].shift(1) >= df['macd_signal'].shift(1))
        df.loc[crossunder, 'signal'] = self.SIGNAL_SELL

        return df

    def on_price_tick(self, price: float, current_position: dict = None, context: dict = None) -> int:
        """Tick intravela liviano (fallback): delega al BaseStrategy."""
        return super().on_price_tick(price, current_position=current_position, context=context)


    def get_features(self) -> List[str]:
        return ['macd', 'macd_signal', 'macd_hist']
