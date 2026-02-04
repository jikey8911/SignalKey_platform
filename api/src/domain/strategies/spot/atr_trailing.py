import numpy as np
import pandas as pd
from typing import List
from api.src.domain.strategies.base import BaseStrategy

class ATRTrailingStrategy(BaseStrategy):
    """
    Usa la volatilidad (Average True Range) para mantenerse en tendencia.
    Compra: Precio cierra muy por encima de la volatilidad reciente.
    """
    def apply(self, df: pd.DataFrame, current_position: dict = None) -> pd.DataFrame:
        period = 14
        multiplier = 3.0
        
        # TR calculation
        df['tr0'] = abs(df['high'] - df['low'])
        df['tr1'] = abs(df['high'] - df['close'].shift())
        df['tr2'] = abs(df['low'] - df['close'].shift())
        df['tr'] = df[['tr0', 'tr1', 'tr2']].max(axis=1)
        df['atr'] = df['tr'].rolling(window=period).mean()

        # Bandas
        df['upper_band'] = df['close'] + (multiplier * df['atr'])
        df['lower_band'] = df['close'] - (multiplier * df['atr'])

        df['signal'] = self.SIGNAL_WAIT

        # Lógica simplificada de ruptura de volatilidad
        # Si el precio rompe el máximo del canal ATR previo
        threshold = df['close'].shift(1) + df['atr'].shift(1)
        df.loc[df['close'] > threshold, 'signal'] = self.SIGNAL_BUY
        
        # Salida si cae del mínimo
        stop_loss = df['close'].shift(1) - df['atr'].shift(1)
        df.loc[df['close'] < stop_loss, 'signal'] = self.SIGNAL_SELL

        return df

    def get_features(self) -> List[str]:
        return ['atr', 'tr']
