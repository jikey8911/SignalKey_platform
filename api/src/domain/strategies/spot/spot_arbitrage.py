import pandas as pd
import numpy as np
from typing import List
from .base import BaseStrategy

class SpotArbitrage(BaseStrategy):
    """
    Estrategia de Arbitraje estadístico basada en Z-Score.
    Identifica anomalías de precio respecto a su media histórica.
    """
    def __init__(self, config=None):
        super().__init__(config or {})
        self.period = self.config.get('period', 20)
        self.z_threshold = self.config.get('z_threshold', 2.0)

    def apply(self, df: pd.DataFrame, current_position: dict = None) -> pd.DataFrame:
        if df.empty or len(df) < self.period:
            return df

        # 1. Cálculos Estadísticos
        df['mean'] = df['close'].rolling(window=self.period).mean()
        df['std'] = df['close'].rolling(window=self.period).std()
        
        # Z-Score: (Precio - Media) / Desviación
        df['z_score'] = (df['close'] - df['mean']) / df['std']
        
        # 2. Features dinámicas
        df['deviation_pct'] = (df['close'] - df['mean']) / df['mean']
        df['volatility_z'] = df['std'].pct_change()

        # 3. Señales ESTÁNDAR
        df['signal'] = self.SIGNAL_WAIT
        
        # LONG: El precio está anormalmente bajo (Z < -threshold)
        df.loc[df['z_score'] <= -self.z_threshold, 'signal'] = self.SIGNAL_BUY
        
        # SHORT: El precio está anormalmente alto (Z > threshold)
        df.loc[df['z_score'] >= self.z_threshold, 'signal'] = self.SIGNAL_SELL
        
        return df

    def get_features(self) -> List[str]:
        return ['z_score', 'deviation_pct', 'volatility_z']