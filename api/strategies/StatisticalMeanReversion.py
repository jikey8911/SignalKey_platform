import pandas as pd
import numpy as np
from .base import BaseStrategy

class StatisticalMeanReversion(BaseStrategy):
    """
    Estrategia basada en la reversión a la media estadística.
    Calcula la volatilidad histórica (Expected Move) y detecta tendencias
    para generar señales y características (features) para modelos de ML.
    """
    def __init__(self, config=None):
        super().__init__(config or {})
        self.name = "StatisticalMeanReversion"
        # Parámetros por defecto para el cálculo estadístico
        self.period = self.config.get('period', 24)
        self.std_dev_multiplier = self.config.get('std_dev', 2.0)
        self.trend_ema = self.config.get('trend_ema', 200)

    def apply(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Aplica indicadores técnicos, define la tendencia y prepara
        las columnas necesarias para el entrenamiento del modelo.
        """
        if df.empty or len(df) < self.trend_ema:
            return df

        # 1. Cálculo de Media Móvil y Bandas de Volatilidad (Expected Move +-X%)
        df['sma'] = df['close'].rolling(window=self.period).mean()
        df['std'] = df['close'].rolling(window=self.period).std()
        
        # Bandas dinámicas basadas en la desviación estándar histórica
        df['upper_band'] = df['sma'] + (df['std'] * self.std_dev_multiplier)
        df['lower_band'] = df['sma'] - (df['std'] * self.std_dev_multiplier)
        
        # Feature: Desviación porcentual respecto a la media
        df['dev_pct'] = (df['close'] - df['sma']) / df['sma']

        # 2. Detección de Tendencia General (EMA 200)
        df['ema_trend'] = df['close'].ewm(span=self.trend_ema, adjust=False).mean()
        df['trend'] = 0  # 0: Neutral, 1: Alcista, -1: Bajista
        
        df.loc[(df['close'] > df['ema_trend']), 'trend'] = 1
        df.loc[(df['close'] < df['ema_trend']), 'trend'] = -1

        # 3. Features Temporales (Para detectar patrones horarios/diarios)
        df['hour'] = df.index.hour
        df['minute'] = df.index.minute
        df['day_week'] = df.index.dayofweek

        # 4. Generación de Señales (Labels para Entrenamiento)
        df['signal'] = 0 # 0: Esperar, 1: Long, 2: Short
        
        # Lógica de entrada basada en bandas y tendencia
        df.loc[(df['close'] < df['lower_band']) & (df['trend'] >= 0), 'signal'] = 1
        df.loc[(df['close'] > df['upper_band']) & (df['trend'] <= 0), 'signal'] = 2

        # 5. Métrica de fuerza relativa para DCA (Dollar Cost Averaging)
        df['relative_strength'] = (df['close'] - df['lower_band']) / (df['upper_band'] - df['lower_band'])

        return df

    def get_features(self):
        """Retorna la lista de columnas que el modelo de ML debe usar."""
        return ['dev_pct', 'trend', 'hour', 'minute', 'day_week', 'relative_strength']