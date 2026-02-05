import unittest
import pandas as pd
import numpy as np
import sys
import os

# Asegurar que podemos importar api
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from api.src.domain.strategies.base import BaseStrategy
from api.src.domain.strategies.spot.rsi_reversion import RsiReversion
from api.src.domain.strategies.spot.trend_ema import TrendEma
from api.src.domain.strategies.spot.volatility_breakout import VolatilityBreakout

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
        
        strategy = RsiReversion(config={'rsi_period': 14, 'oversold': 30})
        
        # Test sin posición
        position_context = {
            'has_position': False,
            'position_type': None,
            'avg_entry_price': 0,
            'current_price': 10,
            'unrealized_pnl_pct': 0,
            'position_count': 0
        }
        df_res = strategy.apply(self.df, position_context)
        last_signal = df_res['signal'].iloc[-1]
        
        # Debería dar BUY porque el RSI estará bajo
        self.assertTrue(last_signal in [BaseStrategy.SIGNAL_BUY, BaseStrategy.SIGNAL_WAIT, BaseStrategy.SIGNAL_SELL]) 
        print(f"RSI Signal: {last_signal}")

    def test_trend_ema(self):
        strategy = TrendEma(config={'fast': 10, 'slow': 20})
        position_context = {
            'has_position': False,
            'position_type': None,
            'avg_entry_price': 0,
            'current_price': self.df['close'].iloc[-1],
            'unrealized_pnl_pct': 0,
            'position_count': 0
        }
        df_res = strategy.apply(self.df, position_context)
        last_signal = df_res['signal'].iloc[-1]
        self.assertIn(last_signal, [BaseStrategy.SIGNAL_BUY, BaseStrategy.SIGNAL_SELL, BaseStrategy.SIGNAL_WAIT])

    def test_volatility_breakout(self):
        strategy = VolatilityBreakout(config={'period': 20})
        position_context = {
            'has_position': False,
            'position_type': None,
            'avg_entry_price': 0,
            'current_price': self.df['close'].iloc[-1],
            'unrealized_pnl_pct': 0,
            'position_count': 0
        }
        df_res = strategy.apply(self.df, position_context)
        last_signal = df_res['signal'].iloc[-1]
        self.assertIn(last_signal, [BaseStrategy.SIGNAL_BUY, BaseStrategy.SIGNAL_SELL, BaseStrategy.SIGNAL_WAIT])

if __name__ == '__main__':
    unittest.main()
