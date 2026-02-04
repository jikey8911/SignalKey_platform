import pandas as pd
from .base import BaseStrategy

class TrendEma(BaseStrategy):
    """
    Estrategia de seguimiento de tendencia mediante cruce de EMAs
    con filtro de volumen para confirmar fuerza.
    """
    def __init__(self, config=None):
        super().__init__(config or {})
        self.fast = 9
        self.slow = 21

    def apply(self, df: pd.DataFrame, current_position: dict = None) -> pd.DataFrame:
        df['ema_f'] = df['close'].ewm(span=self.fast).mean()
        df['ema_s'] = df['close'].ewm(span=self.slow).mean()
        df['vol_sma'] = df['volume'].rolling(window=20).mean()

        # Features
        df['ema_diff'] = (df['ema_f'] - df['ema_s']) / df['ema_s']
        df['vol_ratio'] = df['volume'] / df['vol_sma']

        df['signal'] = self.SIGNAL_WAIT

        # LONG: Cruce alcista + Volumen superior al promedio
        df.loc[(df['ema_f'] > df['ema_s']) & (df['vol_ratio'] > 1.2), 'signal'] = self.SIGNAL_BUY

        # SHORT: Cruce bajista + Volumen superior al promedio
        df.loc[(df['ema_f'] < df['ema_s']) & (df['vol_ratio'] > 1.2), 'signal'] = self.SIGNAL_SELL

        return df

    def get_features(self):
        return ['ema_diff', 'vol_ratio']