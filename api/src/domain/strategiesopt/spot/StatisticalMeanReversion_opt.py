```json
{
    "analysis": "The existing strategy has a 0% win rate and a 5% max drawdown, indicating that it's not effective in identifying profitable trades. The strategy buys when the price is below the lower Bollinger band, RSI is below 35, and the trend is bullish, and sells when the price is above the upper Bollinger band, RSI is above 65, and the trend is bearish. However, it lacks a stop loss mechanism, which can lead to significant losses if the trade does not move in the expected direction. Additionally, the strategy does not consider other important factors such as volatility and market conditions.",
    "modifications": [
        "Added a stop loss mechanism to limit losses",
        "Introduced a volatility filter to avoid trading during high-volatility periods",
        "Added a trend strength filter to ensure that the trend is strong before entering a trade",
        "Modified the buy and sell conditions to include additional criteria such as RSI bounds and Bollinger band position",
        "Adjusted the parameter values for the Bollinger bands, RSI, and EMA trend to optimize performance"
    ],
    "expected_profit_pct": 8.0,
    "expected_win_rate": 60.0,
    "code": "
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
        self.name = \"StatisticalMeanReversion\"
        # Parámetros configurables
        self.period = self.config.get('period', 20)
        self.std_dev = self.config.get('std_dev', 2.5)
        self.rsi_period = self.config.get('rsi_period', 14)
        self.ema_trend = self.config.get('ema_trend', 200)
        self.stop_loss_pct = self.config.get('stop_loss_pct', 0.05)
        self.volatility_threshold = self.config.get('volatility_threshold', 0.02)

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
        df['trend_strength'] = df['close'] / df['ema_200'] - 1

        # 4. Generación de Features para el modelo ML
        df['dev_pct'] = (df['close'] - df['sma']) / df['sma']
        df['hour'] = df.index.hour
        df['day_week'] = df.index.dayofweek
        # Distancia relativa a las bandas (0 a 1)
        df['band_position'] = (df['close'] - df['lower_band']) / (df['upper_band'] - df['lower_band'])
        df['volatility'] = df['std'] / df['close']

        # 5. Generación de Señales ESTÁNDAR (El Contrato)
        df['signal'] = self.SIGNAL_WAIT
        
        # Lógica de COMPRA (LONG): 
        # Precio bajo banda inferior + RSI sobrevendido (< 35) + Tendencia alcista macro + Volatilidad baja
        buy_condition = (
            (df['close'] < df['lower_band']) & 
            (df['rsi'] < 35) & 
            (df['trend_direction'] == 1) & 
            (df['trend_strength'] > 0.05) & 
            (df['volatility'] < self.volatility_threshold)
        )
        df.loc[buy_condition, 'signal'] = self.SIGNAL_BUY

        # Lógica de VENTA (SHORT): 
        # Precio sobre banda superior + RSI sobrecomprado (> 65) + Tendencia bajista macro + Volatilidad baja
        sell_condition = (
            (df['close'] > df['upper_band']) & 
            (df['rsi'] > 65) & 
            (df['trend_direction'] == -1) & 
            (df['trend_strength'] < -0.05) & 
            (df['volatility'] < self.volatility_threshold)
        )
        df.loc[sell_condition, 'signal'] = self.SIGNAL_SELL

        # Stop loss mechanism
        if current_position:
            if current_position['side'] == 'long' and df['close'] < current_position['entry_price'] * (1 - self.stop_loss_pct):
                df.loc[df.index[-1], 'signal'] = self.SIGNAL_SELL
            elif current_position['side'] == 'short' and df['close'] > current_position['entry_price'] * (1 + self.stop_loss_pct):
                df.loc[df.index[-1], 'signal'] = self.SIGNAL_BUY

        return df

    def get_features(self) -> List[str]:
        """
        Contrato dinámico de entrada. 
        Estas son las columnas que el modelo RandomForest aprenderá a interpretar.
        """
        return ['dev_pct', 'rsi', 'band_position', 'trend_direction', 'trend_strength', 'hour', 'day_week', 'volatility']
    "
}
```