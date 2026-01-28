import pandas as pd
import numpy as np
from typing import Dict, Any
from .base import BaseStrategy

class SpotArbitrage(BaseStrategy):
    def __init__(self, period: int = 20, z_threshold: float = 2.0):
        """
        Arbitraje de spot en un solo exchange basado en reversión a la media (Z-Score).
        
        Args:
            period (int): Ventana de tiempo para calcular el precio medio esperado.
            z_threshold (float): Desviación estándar para disparar la operación.
        """
        super().__init__(
            "Spot_Arbitrage_Basic", 
            "Arbitraje por desviación estadística del precio esperado (Básico)"
        )
        self.period = period
        self.z_threshold = z_threshold

    def get_signal(self, data: pd.DataFrame, position_context: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Calcula si el precio actual está lo suficientemente lejos del precio 
        esperado para considerarse una oportunidad de arbitraje.
        """
        close = data['close']
        
        # 1. Calcular el precio esperado (Media Móvil)
        expected_price = close.rolling(window=self.period).mean()
        
        # 2. Calcular la volatilidad (Desviación Estándar)
        std_dev = close.rolling(window=self.period).std()
        
        # 3. Calcular el Z-Score (Cuántas desviaciones se alejó el precio)
        # Z = (Precio Actual - Precio Esperado) / Desviación
        last_close = close.iloc[-1]
        last_expected = expected_price.iloc[-1]
        last_std = std_dev.iloc[-1]
        
        z_score = (last_close - last_expected) / last_std if last_std != 0 else 0
        
        signal = 'hold'
        confidence = min(abs(z_score) / (self.z_threshold * 2), 1.0)
        
        # Lógica de Arbitraje:
        # Si el precio es muy bajo (Z < -threshold), compramos esperando que suba al precio esperado.
        # Si el precio es muy alto (Z > threshold), vendemos esperando que baje al precio esperado.
        if z_score <= -self.z_threshold:
            signal = 'buy'
        elif z_score >= self.z_threshold:
            signal = 'sell'
            
        return {
            'signal': signal,
            'confidence': round(confidence, 2),
            'meta': {
                'z_score': round(z_score, 4),
                'expected_price': round(last_expected, 6),
                'deviation_pct': round(((last_close - last_expected) / last_expected) * 100, 2)
            }
        }
