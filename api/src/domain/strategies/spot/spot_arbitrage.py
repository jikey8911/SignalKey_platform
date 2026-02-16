import pandas as pd
import numpy as np
from typing import List
from api.src.domain.strategies.base import BaseStrategy

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
        
        # Reemplazar infinitos (cuando std es 0) por NaN
        df.replace([np.inf, -np.inf], np.nan, inplace=True)

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

    def on_price_tick(self, price: float, current_position: dict = None, context: dict = None) -> int:
        """Tick rápido arbitraje: fallback neutro (evitar falsas señales sin zscore en vivo)."""
        return self.SIGNAL_WAIT

    def get_features(self) -> List[str]:
        return ['z_score', 'deviation_pct', 'volatility_z']