
import unittest
import pandas as pd
import numpy as np
import sys
import os

# Add api to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from api.ml.strategy_trainer import StrategyTrainer

class TestStrategyTrainer(unittest.TestCase):
    def setUp(self):
        # Create synthetic data specific for trends
        # 200 candles
        self.df = pd.DataFrame({
            'timestamp': pd.date_range(start='2023-01-01', periods=200, freq='h'),
            'open': [100] * 200,
            'high': [105] * 200,
            'low': [95] * 200,
            'close': list(range(100, 300)) if len(range(100, 300)) == 200 else [100 + i for i in range(200)], # Strong Uptrend
            'volume': [1000] * 200
        })
        
        # Ensure we have enough data for indicators (need ~60-100 rows warmup)
        
    def test_generate_labeled_dataset_accumulation(self):
        """
        Test that StrategyTrainer can process a dataset and identify profitable strategies.
        Crucially, it should not crash with the new accumulation logic (removed position_size check).
        """
        trainer = StrategyTrainer(self.df, initial_balance=10000, use_virtual_balance=True)
        
        # Generate dataset
        # This calls _execute_virtual_trade which we modified
        try:
            labeled_df = trainer.generate_labeled_dataset(window_size=60, forecast_horizon=12)
        except Exception as e:
            self.fail(f"generate_labeled_dataset failed with error: {e}")
            
        print(f"Generated {len(labeled_df)} labeled samples")
        
        # In a strong uptrend, TrendEMA or RSI (if dipping) or simply HOLD might be best.
        # We mostly care that it generated rows and didn't fail on "position_size" logic.
        self.assertGreater(len(labeled_df), 0, "Should generate labeled data")
        
        # Check columns
        expected_cols = ['rsi', 'adx', 'atr_pct', 'bb_width', 'vol_rel', 'label', 'timestamp']
        for col in expected_cols:
            self.assertIn(col, labeled_df.columns, f"Missing column {col}")
            
        # Verify labels are integers (Strategy IDs)
        self.assertTrue(pd.api.types.is_integer_dtype(labeled_df['label']), "Label should be integer")

if __name__ == '__main__':
    unittest.main()
