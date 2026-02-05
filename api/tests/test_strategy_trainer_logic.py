import unittest
import pandas as pd
import numpy as np
import sys
import os

# Add project root to path (parent of 'api')
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from api.src.domain.services.strategy_trainer import StrategyTrainer

class TestStrategyTrainerLogic(unittest.TestCase):
    def setUp(self):
        # Create dummy data
        data = {
            'timestamp': pd.date_range(start='2023-01-01', periods=100, freq='H'),
            'open': np.random.rand(100) * 100,
            'high': np.random.rand(100) * 100,
            'low': np.random.rand(100) * 100,
            'close': np.random.rand(100) * 100,
            'volume': np.random.rand(100) * 1000
        }
        self.df = pd.DataFrame(data)
        self.trainer = StrategyTrainer(self.df, initial_balance=10000.0, use_virtual_balance=True)

    def test_accumulation_logic(self):
        """Test increasing position size on same signal (Accumulation) - Verify PnL logic"""
        # StrategyTrainer resets position after trade, so we must simulate state manually
        # to test accumulation "math".
        
        # Scenario: Existing Position
        # Own 100 coins at $100. Total Cost $10,000.
        self.trainer.virtual_balance = 10000.0
        self.trainer.position_size = 100.0 
        self.trainer.position_entry_price = 100.0
        
        entry_price_new = 110.0
        exit_price = 120.0
        fee = 0.000 # Simplify math for test check
        
        # Execute BUY (Accumulate)
        # Should invest 95% of 10000 = 9500
        # New Coins = 9500 / 110 = 86.3636...
        # Total Coins = 100 + 86.3636 = 186.3636
        # Total Cost = 10000 (old) + 9500 (new) = 19500
        # Avg Entry = 19500 / 186.3636 = 104.634...
        
        # Exit Value = 186.3636 * 120 = 22363.636
        # PnL = (22363.636 - 19500) / 19500 = 0.1468... (14.68%)
        
        pnl = self.trainer._execute_virtual_trade('buy', entry_price_new, exit_price, fee)
        
        # Expected calculation
        trade_amt = 10000.0 * 0.95
        new_coins = trade_amt / entry_price_new
        total_coins = 100.0 + new_coins
        total_invested = trade_amt + (100.0 * 100.0) # New Invest (9500) + Old Cost Basis (10000)
        
        exit_val = total_coins * exit_price
        expected_pnl = (exit_val - total_invested) / total_invested
        
        print(f"Accum PnL: {pnl}, Expected: {expected_pnl}")
        self.assertAlmostEqual(pnl, expected_pnl, places=4)
        
        # Verify it reset (as expected by design)
        self.assertEqual(self.trainer.position_size, 0)
        
    def test_inverse_closing_logic(self):
        """Test closing position immediately on opposite signal"""
        entry_price = 100.0
        fee = 0.001
        
        # 1. Start with a LONG position
        self.trainer.virtual_balance = 500.0 # Cash
        self.trainer.position_size = 10.0 # 10 coins
        self.trainer.position_entry_price = 100.0 # Cost basis 1000
        
        # 2. Receive SELL signal
        # Should sell 10 coins at CURRENT price (entry_price arg in execute_trade becomes current price)
        current_price_sell = 105.0 # We made profit
        
        # Note: _execute_virtual_trade args are (signal, entry_price, exit_price, fee)
        # When called from loop: execute_trade(signal, current_price, future_price)
        # For SELL on LONG: we sell at 'entry_price' (which is current_price in the loop context)
        
        pnl = self.trainer._execute_virtual_trade('sell', current_price_sell, 100.0, fee)
        
        # Check Position is closed
        self.assertEqual(self.trainer.position_size, 0)
        self.assertEqual(self.trainer.position_entry_price, 0)
        
        # Check Balance increased (Original 500 + Sale Proceeds)
        # Sale: 10 * 105 = 1050
        # Fee: 1.05
        # Net: 1048.95
        # New Bal: 500 + 1048.95 = 1548.95
        expected_bal = 500.0 + (10 * 105.0 * (1 - fee))
        self.assertAlmostEqual(self.trainer.virtual_balance, expected_bal, places=2)
        
        print(f"Closed Balance: {self.trainer.virtual_balance}, PnL: {pnl}")
        
    def test_break_even_calculation(self):
        """Test break-even price calculation logic (context simulation)"""
        # This logic is inside generate_labeled_dataset loop, not a standalone method yet.
        # But we implemented the formula: Entry * (1 + fee) / (1 - fee)
        
        entry = 100.0
        fee = 0.001
        
        be_price = entry * (1 + fee) / (1 - fee)
        
        # Manual calc:
        # Cost = 100 * 1.001 = 100.1
        # Target Revenue needed = 100.1
        # Price * (1 - 0.001) = 100.1
        # Price = 100.1 / 0.999 = 100.2002
        
        print(f"Entry: {entry}, Fee: {fee}, Break-Even: {be_price}")
        self.assertAlmostEqual(be_price, 100.2002002, places=4)

if __name__ == '__main__':
    unittest.main()
