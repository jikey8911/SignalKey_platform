import pandas as pd
import numpy as np
from api.src.domain.strategies.base import BaseStrategy

class SpotIntraExchangeArbitrage(BaseStrategy):
    """
    Basada en tu lógica de Z-Score.
    Mejora: Adaptada al contrato de IA y ejecución automática con filtros de volatilidad.
    """
    def __init__(self, config=None):
        super().__init__(config or {})
        self.period = self.config.get('period', 20)
        self.z_threshold = self.config.get('z_threshold', 2.0)

    def apply(self, df: pd.DataFrame, current_position: dict = None) -> pd.DataFrame:
        if len(df) < self.period: return df

        # Lógica de Z-Score
        df['avg'] = df['close'].rolling(self.period).mean()
        df['std'] = df['close'].rolling(self.period).std()
        df['z_score'] = (df['close'] - df['avg']) / df['std']
        
        # Reemplazar infinitos (cuando std es 0) por NaN
        df.replace([np.inf, -np.inf], np.nan, inplace=True)

        # Features dinámicas para que la IA entienda el contexto
        df['volatility_index'] = df['std'] / df['avg']
        df['distance_pct'] = (df['close'] - df['avg']) / df['avg']

        # Señal ESTÁNDAR
        df['signal'] = self.SIGNAL_WAIT
        
        # Arbitraje estadístico puro:
        df.loc[df['z_score'] <= -self.z_threshold, 'signal'] = self.SIGNAL_BUY
        df.loc[df['z_score'] >= self.z_threshold, 'signal'] = self.SIGNAL_SELL

        return df

    def on_price_tick(self, price: float, current_position: dict = None, context: dict = None) -> int:
        """Tick intravela liviano (fallback): delega al BaseStrategy."""
        return super().on_price_tick(price, current_position=current_position, context=context)


    def get_features(self):
        return ['z_score', 'volatility_index', 'distance_pct']