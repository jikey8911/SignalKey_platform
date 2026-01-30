import pandas as pd
import numpy as np
from .base import BaseStrategy

class SpotIntraExchangeArbitrage(BaseStrategy):
    """
    Basada en tu lógica de Z-Score.
    Mejora: Adaptada al contrato de IA y ejecución automática con filtros de volatilidad.
    """
    def __init__(self, config=None):
        super().__init__(config or {})
        self.period = self.config.get('period', 20)
        self.z_threshold = self.config.get('z_threshold', 2.0)

    def apply(self, df: pd.DataFrame) -> pd.DataFrame:
        if len(df) < self.period: return df

        # Lógica de Z-Score
        df['avg'] = df['close'].rolling(self.period).mean()
        df['std'] = df['close'].rolling(self.period).std()
        df['z_score'] = (df['close'] - df['avg']) / df['std']
        
        # Features dinámicas para que la IA entienda el contexto
        df['volatility_index'] = df['std'] / df['avg']
        df['distance_pct'] = (df['close'] - df['avg']) / df['avg']

        # Señal ESTÁNDAR
        df['signal'] = self.SIGNAL_WAIT
        
        # Arbitraje estadístico puro:
        df.loc[df['z_score'] <= -self.z_threshold, 'signal'] = self.SIGNAL_BUY
        df.loc[df['z_score'] >= self.z_threshold, 'signal'] = self.SIGNAL_SELL

        return df

    def get_features(self):
        return ['z_score', 'volatility_index', 'distance_pct']