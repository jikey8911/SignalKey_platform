from api.src.domain.strategies.base import BaseStrategy
import os
import importlib
import inspect
import sys
import logging

logger = logging.getLogger(__name__)

__all__ = ['BaseStrategy', 'load_strategies']

def load_strategies(market_type: str = None):
    """
    Dynamically loads all strategy classes from the strategies directory and market subdirectories.
    Returns:
        dict: { 'StrategyName': StrategyInstance }
        list: [StrategyInstance] sorted by name (for consistent ID mapping)
    """
    strategies = {}
    
    # ensure current directory is in path
    current_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Paths to search: root and market-specific
    search_paths = [current_dir]
    if market_type:
        market_dir = os.path.join(current_dir, market_type.lower())
        if os.path.exists(market_dir):
            search_paths.append(market_dir)

    for base_path in search_paths:
        if not os.path.exists(base_path):
            continue

        is_subdir = base_path != current_dir

        for filename in os.listdir(base_path):
            if filename.endswith(".py") and filename not in ["__init__.py", "base.py"]:
                module_name = filename[:-3]
                try:
                    # Import module
                    if is_subdir:
                        full_module_name = f"api.src.domain.strategies.{market_type.lower()}.{module_name}"
                    else:
                        full_module_name = f"api.src.domain.strategies.{module_name}"

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
                    logger.error(f"Error loading strategy from {filename} in {base_path}: {e}")
                    continue
                
    # Sort for deterministic ordering (critical for ML model ID mapping)
    sorted_strategies = sorted(list(strategies.values()), key=lambda s: s.__class__.__name__)
    
    return strategies, sorted_strategies
