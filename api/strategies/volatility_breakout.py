import pandas as pd
from .base import BaseStrategy

class VolatilityBreakout(BaseStrategy):
    """
    Estrategia de ruptura basada en Canales de Donchian y ATR.
    Busca capturar el inicio de movimientos explosivos.
    """
    def __init__(self, config=None):
        super().__init__(config or {})
        self.period = 20

    def apply(self, df: pd.DataFrame) -> pd.DataFrame:
        df['upper_channel'] = df['high'].rolling(window=self.period).max()
        df['lower_channel'] = df['low'].rolling(window=self.period).min()
        
        # ATR para medir expansión de volatilidad
        df['tr'] = pd.concat([df['high'] - df['low'], 
                             (df['high'] - df['close'].shift()).abs(), 
                             (df['low'] - df['close'].shift()).abs()], axis=1).max(axis=1)
        df['atr'] = df['tr'].rolling(window=14).mean()
        
        # Features
        df['dist_upper'] = (df['upper_channel'] - df['close']) / df['close']
        df['atr_pct'] = df['atr'] / df['close']

        df['signal'] = self.SIGNAL_WAIT
        
        # LONG: Ruptura del canal superior
        df.loc[df['close'] >= df['upper_channel'].shift(), 'signal'] = self.SIGNAL_BUY
        
        # SHORT: Ruptura del canal inferior
        df.loc[df['close'] <= df['lower_channel'].shift(), 'signal'] = self.SIGNAL_SELL
        
        return df

    def get_features(self):
        return ['dist_upper', 'atr_pct']