import pandas as pd
import numpy as np
from typing import List
from api.src.domain.strategies.base import BaseStrategy

class StatisticalMeanReversion(BaseStrategy):
    """
    Estrategia de Reversión a la Media Optimizada.
    Utiliza Bandas de Bollinger, RSI y filtros de tendencia para mejorar el Win Rate.
    Implementa el contrato dinámico de features y señales estándar de la plataforma.
    """
    def __init__(self, config=None):
        super().__init__(config or {})
        self.name = "StatisticalMeanReversion"
        # Parámetros configurables
        self.period = self.config.get('period', 20)
        self.std_dev = self.config.get('std_dev', 2.0)
        self.rsi_period = self.config.get('rsi_period', 14)
        self.ema_trend = self.config.get('ema_trend', 200)

    def apply(self, df: pd.DataFrame, current_position: dict = None) -> pd.DataFrame:
        """
        Calcula indicadores técnicos avanzados y genera señales estandarizadas.
        """
        if df.empty or len(df) < self.ema_trend:
            return df

        # 1. Indicadores de Volatilidad (Bandas de Bollinger)
        df['sma'] = df['close'].rolling(window=self.period).mean()
        df['std'] = df['close'].rolling(window=self.period).std()
        df['upper_band'] = df['sma'] + (df['std'] * self.std_dev)
        df['lower_band'] = df['sma'] - (df['std'] * self.std_dev)
        
        # 2. Indicador de Momentum (RSI)
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=self.rsi_period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=self.rsi_period).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))

        # 3. Filtro de Tendencia Macro
        df['ema_200'] = df['close'].ewm(span=self.ema_trend, adjust=False).mean()
        df['trend_direction'] = 0
        df.loc[df['close'] > df['ema_200'], 'trend_direction'] = 1  # Alcista
        df.loc[df['close'] < df['ema_200'], 'trend_direction'] = -1 # Bajista

        # 4. Generación de Features para el modelo ML
        df['dev_pct'] = (df['close'] - df['sma']) / df['sma']
        df['hour'] = df.index.hour
        df['day_week'] = df.index.dayofweek
        # Distancia relativa a las bandas (0 a 1)
        df['band_position'] = (df['close'] - df['lower_band']) / (df['upper_band'] - df['lower_band'])

        # 5. Generación de Señales ESTÁNDAR (El Contrato)
        df['signal'] = self.SIGNAL_WAIT
        
        # Lógica de COMPRA (LONG): 
        # Precio bajo banda inferior + RSI sobrevendido (< 35) + Tendencia alcista macro
        buy_condition = (
            (df['close'] < df['lower_band']) & 
            (df['rsi'] < 35) & 
            (df['trend_direction'] == 1)
        )
        df.loc[buy_condition, 'signal'] = self.SIGNAL_BUY

        # Lógica de VENTA (SHORT): 
        # Precio sobre banda superior + RSI sobrecomprado (> 65) + Tendencia bajista macro
        sell_condition = (
            (df['close'] > df['upper_band']) & 
            (df['rsi'] > 65) & 
            (df['trend_direction'] == -1)
        )
        df.loc[sell_condition, 'signal'] = self.SIGNAL_SELL

        return df

    def on_price_tick(self, price: float, current_position: dict = None, context: dict = None) -> int:
        """Tick intravela liviano (fallback): delega al BaseStrategy."""
        return super().on_price_tick(price, current_position=current_position, context=context)


    def get_features(self) -> List[str]:
        """
        Contrato dinámico de entrada. 
        Estas son las columnas que el modelo RandomForest aprenderá a interpretar.
        """
        return ['dev_pct', 'rsi', 'band_position', 'trend_direction', 'hour', 'day_week']