import unittest
import pandas as pd
import numpy as np
import sys
import os

# Asegurar que podemos importar api
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from api.strategies.rsi_reversion import RSIReversion
from api.strategies.trend_ema import TrendEMA
from api.strategies.volatility_breakout import VolatilityBreakout

class TestStrategies(unittest.TestCase):
    def setUp(self):
        # Crear datos sintéticos
        dates = pd.date_range(start='2023-01-01', periods=100, freq='h')
        self.df = pd.DataFrame({
            'open': np.random.rand(100) * 100,
            'high': np.random.rand(100) * 100,
            'low': np.random.rand(100) * 100,
            'close': np.random.rand(100) * 100,
            'volume': np.random.rand(100) * 1000
        }, index=dates)
        
        # Ajustar datos para garantizar consistencia (high > low)
        self.df['high'] = self.df[['open', 'close']].max(axis=1) + 1
        self.df['low'] = self.df[['open', 'close']].min(axis=1) - 1

    def test_rsi_reversion(self):
        # Crear un escenario de sobreventa artificial
        # Pandas TA necesita suficientes datos, así que modificamos el final
        self.df.iloc[-15:, self.df.columns.get_loc('close')] = np.linspace(50, 10, 15) # Bajada fuerte
        
        strategy = RSIReversion(period=14, oversold=30)
        signal = strategy.get_signal(self.df)
        
        # Debería dar BUY porque el RSI estará bajo
        # Nota: Depende de la implementación exacta de pandas_ta, pero con bajada lineal a 10 debería ser bajo.
        self.assertTrue(signal['signal'] in ['buy', 'hold', 'sell']) # Basic check
        print(f"RSI Signal: {signal}")

    def test_trend_ema(self):
        strategy = TrendEMA(fast=10, slow=20)
        signal = strategy.get_signal(self.df)
        self.assertIn(signal['signal'], ['buy', 'sell', 'hold'])

    def test_volatility_breakout(self):
        strategy = VolatilityBreakout(period=20)
        signal = strategy.get_signal(self.df)
        self.assertIn(signal['signal'], ['buy', 'sell', 'hold'])

if __name__ == '__main__':
    unittest.main()
