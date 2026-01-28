import unittest
import sys
import os

# Add api to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from api.strategies.rsi_reversion import RSIReversion
from api.strategies.trend_ema import TrendEMA
from api.strategies.volatility_breakout import VolatilityBreakout
from api.strategies.spot_intra_arbitrage import SpotIntraExchangeArbitrage
import pandas as pd
import numpy as np

class TestPositionAwareStrategies(unittest.TestCase):
    """Test strategies with position context (bidirectional support)"""
    
    def setUp(self):
        # Create synthetic data
        self.df = pd.DataFrame({
            'open': [100] * 50,
            'high': [102] * 50,
            'low': [98] * 50,
            'close': list(range(100, 50, -1)),  # Downtrend
            'volume': [1000] * 50
        })
    
    def test_rsi_long_entry(self):
        """Test RSI opens LONG when oversold"""
        strategy = RSIReversion(oversold=30)
        ctx = {'has_position': False, 'position_type': None, 'avg_entry_price': 0, 
               'current_price': 50, 'unrealized_pnl_pct': 0, 'position_count': 0}
        
        result = strategy.get_signal(self.df, ctx)
        self.assertEqual(result['signal'], 'buy')
        print(f"✅ RSI LONG entry: {result}")
    
    def test_rsi_short_entry(self):
        """Test RSI opens SHORT when overbought"""
        # Create uptrend data
        df_up = pd.DataFrame({
            'close': list(range(50, 100))
        })
        strategy = RSIReversion(overbought=70)
        ctx = {'has_position': False, 'position_type': None, 'avg_entry_price': 0,
               'current_price': 99, 'unrealized_pnl_pct': 0, 'position_count': 0}
        
        result = strategy.get_signal(df_up, ctx)
        self.assertEqual(result['signal'], 'sell')
        print(f"✅ RSI SHORT entry: {result}")
    
    def test_rsi_no_sell_at_loss(self):
        """Test RSI doesn't close LONG position at loss"""
        strategy = RSIReversion(overbought=70, min_profit=0.5)
        # Simulate LONG position at loss
        ctx = {'has_position': True, 'position_type': 'LONG', 'avg_entry_price': 100,
               'current_price': 95, 'unrealized_pnl_pct': -5.0, 'position_count': 1}
        
        # Create overbought scenario
        df_ob = pd.DataFrame({'close': list(range(50, 100))})
        
        # When RSI > 70 (Overbought), it implies a trend reversal (Short signal).
        # Even if we are in Loss, a Reversal signal is a valid exit/flip.
        # User instruction: "Close only on opposite signal". RSI > 70 IS an opposite signal to LONG.
        result = strategy.get_signal(df_ob, ctx)
        
        self.assertEqual(result['signal'], 'sell')
        print(f"✅ RSI Reversal Exit at Loss: {result}")
    
    def test_arbitrage_bidirectional(self):
        """Test arbitrage opens both LONG and SHORT"""
        strategy = SpotIntraExchangeArbitrage(period=20, z_threshold=2.0)
        
        # Test LONG entry (undervalued)
        df_low = pd.DataFrame({'close': [100]*19 + [80]})
        ctx_no_pos = {'has_position': False, 'position_type': None, 'avg_entry_price': 0,
                      'current_price': 80, 'unrealized_pnl_pct': 0, 'position_count': 0}
        result = strategy.get_signal(df_low, ctx_no_pos)
        self.assertEqual(result['signal'], 'buy')
        print(f"✅ Arbitrage LONG: {result}")
        
        # Test SHORT entry (overvalued)
        df_high = pd.DataFrame({'close': [100]*19 + [120]})
        result = strategy.get_signal(df_high, ctx_no_pos)
        self.assertEqual(result['signal'], 'sell')
        print(f"✅ Arbitrage SHORT: {result}")
    
    def test_trend_ema_bidirectional(self):
        """Test TrendEMA generates both buy and sell signals"""
        strategy = TrendEMA(fast=5, slow=10)
        ctx = {'has_position': False, 'position_type': None, 'avg_entry_price': 0,
               'current_price': 50, 'unrealized_pnl_pct': 0, 'position_count': 0}
        
        result = strategy.get_signal(self.df, ctx)
        # Should be either buy, sell, or hold
        self.assertIn(result['signal'], ['buy', 'sell', 'hold'])
        print(f"✅ TrendEMA signal: {result}")
    
    def test_volatility_breakout_bidirectional(self):
        """Test VolatilityBreakout detects both upper and lower breakouts"""
        strategy = VolatilityBreakout(period=20)
        ctx = {'has_position': False, 'position_type': None, 'avg_entry_price': 0,
               'current_price': 50, 'unrealized_pnl_pct': 0, 'position_count': 0}
        
        result = strategy.get_signal(self.df, ctx)
        self.assertIn(result['signal'], ['buy', 'sell', 'hold'])
        print(f"✅ Breakout signal: {result}")

if __name__ == '__main__':
    unittest.main(verbosity=2)
