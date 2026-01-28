
import pandas as pd
import numpy as np
import asyncio
import logging
import sys
import os

# Add project root to path
sys.path.append(os.getcwd())

from api.strategies import load_strategies
from api.ml.strategy_trainer import StrategyTrainer

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_diversity():
    print("--- 1. Checking Strategy Loading ---")
    strat_dict, strat_list = load_strategies()
    print(f"Found {len(strat_list)} strategies:")
    for i, s in enumerate(strat_list):
        print(f"  ID {i+1}: {s.name} ({s.__class__.__name__})")
        
    if len(strat_list) <= 1:
        print("!! WARNING: Only 0 or 1 strategy found. BaseStrategy might be included or others missing.")
    
    print("\n--- 2. Testing StrategyTrainer Diversity ---")
    # Generate synthetic volatile data to force different strategies to win
    # Sine waves with different frequencies/phases to simulate trends vs range
    length = 500
    t = np.linspace(0, 100, length)
    price = 100 + 10 * np.sin(t) + 5 * np.sin(3*t) + np.random.normal(0, 1, length) # Volatile
    
    df = pd.DataFrame({
        'timestamp': pd.date_range(start='2024-01-01', periods=length, freq='1h'),
        'open': price,
        'high': price + 2,
        'low': price - 2,
        'close': price + np.random.normal(0, 1, length),
        'volume': np.random.randint(100, 1000, length)
    })
    
    trainer = StrategyTrainer(df, initial_balance=10000)
    
    print("Generating labeled dataset...")
    # Reduce window size for this small test
    labeled_df = trainer.generate_labeled_dataset(window_size=20, forecast_horizon=5)
    
    if labeled_df.empty:
        print("!! ERROR: No samples generated.")
        return

    print("\n--- 3. Label Distribution ---")
    counts = labeled_df['label'].value_counts().sort_index()
    print("Label Counts (0=HOLD, 1..N=Strategy ID):")
    print(counts)
    
    total = len(labeled_df)
    for label, count in counts.items():
        name = "HOLD" if label == 0 else strat_list[label-1].name
        pct = (count / total) * 100
        print(f"  Label {label} ({name}): {count} ({pct:.1f}%)")
        
    if len(counts) > 1:
        print("\n✅ SUCCESS: Multiple strategies selected. Model has diversity.")
    else:
        print("\n❌ FAILURE: Only one label selected. Check fees, logic, or data.")

if __name__ == "__main__":
    asyncio.run(test_diversity())
