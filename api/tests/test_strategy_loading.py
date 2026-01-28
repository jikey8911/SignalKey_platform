import unittest
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from api.strategies import load_strategies
from api.strategies.base import BaseStrategy

class TestStrategyLoading(unittest.TestCase):
    def test_dynamic_loading(self):
        """Test that all strategies in the directory are loaded except base.py"""
        strategies_dict, strategies_list = load_strategies()
        
        print(f"Loaded {len(strategies_list)} strategies:")
        for s in strategies_list:
            print(f" - {s.name} ({s.__class__.__name__})")
            
        # Expected strategies based on file list:
        # 1. RSIReversion
        # 2. TrendEMA
        # 3. VolatilityBreakout
        # 4. SpotIntraExchangeArbitrage (from spot_intra_arbitrage.py)
        # 5. SpotArbitrage_Basic (from spot_arbitrage.py - REFACTORIZED)
        
        expected_count = 5
        self.assertEqual(len(strategies_list), expected_count, f"Expected {expected_count} strategies, found {len(strategies_list)}")
        
        # Verify specific classes are present
        class_names = [s.__class__.__name__ for s in strategies_list]
        self.assertIn('RSIReversion', class_names)
        self.assertIn('TrendEMA', class_names)
        self.assertIn('VolatilityBreakout', class_names)
        self.assertIn('SpotIntraExchangeArbitrage', class_names)
        self.assertIn('SpotArbitrage', class_names) # Renamed class
        
        # Verify BaseStrategy is NOT in the list
        for s in strategies_list:
            self.assertNotIsInstance(s, type(BaseStrategy), "BaseStrategy class properly should not be instantiated directly")
            self.assertNotEqual(s.__class__.__name__, 'BaseStrategy')

if __name__ == '__main__':
    unittest.main()
