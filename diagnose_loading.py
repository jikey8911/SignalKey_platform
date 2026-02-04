import sys
import os
import logging

# Add project root
sys.path.append(os.getcwd())

from api.src.domain.services.strategy_trainer import StrategyTrainer

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("StrategyTrainer")
logger.setLevel(logging.INFO)

def test_load():
    trainer = StrategyTrainer()
    
    print("--- Testing VWAP Loading ---")
    klass = trainer.load_strategy_class("vwap", "spot")
    if klass:
        print(f"✅ SUCCESS: Loaded {klass.__name__}")
    else:
        print("❌ FAILED to load vwap")

    print("\n--- Testing MACD Loading ---")
    klass = trainer.load_strategy_class("macd", "spot")
    if klass:
        print(f"✅ SUCCESS: Loaded {klass.__name__}")
    else:
        print("❌ FAILED to load macd")

if __name__ == "__main__":
    test_load()
