import pandas as pd
import numpy as np
from typing import List, Dict
from api.src.domain.strategies.base import BaseStrategy

class SniperStrategy(BaseStrategy):
    """
    Estrategia optimizada para entradas precisas (Sniper).
    Busca condiciones de alta probabilidad combinando RSI y volatilidad.
    """
    def __init__(self, config=None):
        super().__init__(config or {})
        self.rsi_period = self.config.get('rsi_period', 14)
        self.rsi_overbought = self.config.get('rsi_overbought', 70)
        self.rsi_oversold = self.config.get('rsi_oversold', 30)

    def apply(self, df: pd.DataFrame, current_position: dict = None) -> pd.DataFrame:
        # 1. Cálculo de RSI
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=self.rsi_period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=self.rsi_period).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))

        # 2. Cálculo de Volatilidad (ATR resumido)
        df['tr'] = df[['high', 'low', 'close']].max(axis=1) - df[['high', 'low', 'close']].min(axis=1)
        df['volatility'] = df['tr'].rolling(window=self.rsi_period).mean()

        # 3. Señal SNIPER
        df['signal'] = self.SIGNAL_WAIT

        # Compra: Sobrevendido + RSI subiendo + baja volatilidad (acumulación)
        df.loc[(df['rsi'] < self.rsi_oversold) & (df['rsi'] > df['rsi'].shift(1)), 'signal'] = self.SIGNAL_BUY
        
        # Venta: Sobrecomprado + RSI bajando
        df.loc[(df['rsi'] > self.rsi_overbought) & (df['rsi'] < df['rsi'].shift(1)), 'signal'] = self.SIGNAL_SELL

        return df

    def get_features(self) -> List[str]:
        return ['rsi', 'volatility']

    def build_prompt(self, window: List[dict], current_price: float) -> str:
        """
        Construye el prompt específico para la estrategia Sniper (Legacy/AI)
        """
        return f"""
        Estrategia SNIPER activada. Analiza la siguiente ventana de precios (últimas 10 velas) buscando entradas de alta precisión.
        
        Precio Actual: {current_price}
        
        Datos:
        {window}
        
        Reglas SNIPER:
        - Busca divergencias RSI
        - Busca patrones de velas de reversión claros (martillo, estrella fugaz)
        - Solo opera si el riesgo/beneficio es > 1:3
        - Entradas limit preferidas
        
        Devuelve formato JSON estándar.
        """
