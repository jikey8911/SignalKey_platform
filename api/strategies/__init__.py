from .base import BaseStrategy
from .rsi_reversion import RsiReversion as RSIReversion
from .trend_ema import TrendEma as TrendEMA
from .volatility_breakout import VolatilityBreakout
import os
import importlib
import inspect
import sys
import logging

logger = logging.getLogger(__name__)

__all__ = ['BaseStrategy', 'RSIReversion', 'TrendEMA', 'VolatilityBreakout', 'load_strategies']

def load_strategies():
    """
    Dynamically loads all strategy classes from the strategies directory.
    Returns:
        dict: { 'StrategyName': StrategyInstance }
        list: [StrategyInstance] sorted by name (for consistent ID mapping)
    """
    strategies = {}
    
    # ensure current directory is in path
    current_dir = os.path.dirname(os.path.abspath(__file__))
    
    for filename in os.listdir(current_dir):
        if filename.endswith(".py") and filename not in ["__init__.py", "base.py"]:
            module_name = filename[:-3]
            try:
                # Import module
                # Note: This assumes api.strategies package structure
                full_module_name = f"api.strategies.{module_name}"
                
                if full_module_name in sys.modules:
                     module = sys.modules[full_module_name]
                else:
                     module = importlib.import_module(full_module_name)
                
                # Scan for BaseStrategy subclasses
                for name, obj in inspect.getmembers(module):
                    if inspect.isclass(obj) and issubclass(obj, BaseStrategy) and obj is not BaseStrategy:
                        # Instantiate
                        instance = obj()
                        strategies[name] = instance
            except Exception as e:
                logger.error(f"Error loading strategy from {filename}: {e}")
                continue
                
    # Sort for deterministic ordering (critical for ML model ID mapping)
    sorted_strategies = sorted(list(strategies.values()), key=lambda s: s.__class__.__name__)
    
    return strategies, sorted_strategies
