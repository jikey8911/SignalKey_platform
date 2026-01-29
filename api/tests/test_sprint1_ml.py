import pytest
import pandas as pd
import numpy as np
import os
import shutil
from unittest.mock import MagicMock, patch
from api.ml.strategy_trainer import StrategyTrainer

# Dummy Strategy for testing
DUMMY_STRATEGY_CODE = """
import pandas as pd
from .base import BaseStrategy

class TestStrategy(BaseStrategy):
    def __init__(self, config=None):
        super().__init__(config or {})
        self.name = "TestStrategy"

    def apply(self, df: pd.DataFrame) -> pd.DataFrame:
        df['signal'] = 0
        df.loc[df['close'] > df['open'], 'signal'] = 1
        df['feature1'] = df['close'] / df['open']
        return df

    def get_features(self):
        return ['feature1']
"""

@pytest.fixture
def setup_strategies(tmp_path):
    # Create temp strategies dir
    strategies_dir = tmp_path / "strategies"
    strategies_dir.mkdir()
    
    # Create base.py
    base_py = strategies_dir / "base.py"
    base_py.write_text("class BaseStrategy:\n    def __init__(self, config): pass\n    def apply(self, df): return df\n")
    
    # Create TestStrategy.py
    (strategies_dir / "TestStrategy.py").write_text(DUMMY_STRATEGY_CODE)
    
    # Create models dir
    models_dir = tmp_path / "models"
    models_dir.mkdir()
    
    return strategies_dir, models_dir

@pytest.fixture
def mock_data():
    dates = pd.date_range(start='2023-01-01', periods=100, freq='H')
    df = pd.DataFrame({
        'timestamp': dates,
        'open': np.random.uniform(100, 200, 100),
        'high': np.random.uniform(200, 250, 100),
        'low': np.random.uniform(50, 100, 100),
        'close': np.random.uniform(100, 200, 100),
        'volume': np.random.uniform(1000, 5000, 100)
    })
    return {'BTC/USDT': df, 'ETH/USDT': df.copy()}

def test_discovery(setup_strategies):
    import sys
    # We need to hack sys.modules or patch os.listdir and importlib logic
    # Since StrategyTrainer uses dynamic imports assuming api.strategies..., 
    # testing it with tmp dir is tricky without changing pythonpath.
    # Instead, we will mock the methods of StrategyTrainer.
    pass

@patch('api.ml.strategy_trainer.os.listdir')
def test_discover_strategies_mock(mock_listdir):
    mock_listdir.return_value = ['TestStrategy.py', 'base.py', '__init__.py']
    trainer = StrategyTrainer()
    strategies = trainer.discover_strategies()
    assert 'TestStrategy' in strategies
    assert 'base' not in strategies
    assert '__init__' not in strategies

@patch('api.ml.strategy_trainer.importlib.import_module')
def test_load_strategy_class(mock_import):
    trainer = StrategyTrainer()
    
    from types import SimpleNamespace
    # Mock module structure using SimpleNamespace to avoid auto-creation of attributes
    mock_module = SimpleNamespace()
    # Mock class
    MockStrategy = type('TestStrategy', (), {})
    mock_module.TestStrategy = MockStrategy
    
    mock_import.return_value = mock_module
    
    cls = trainer.load_strategy_class('TestStrategy')
    assert cls == MockStrategy
    mock_import.assert_called_with('api.strategies.TestStrategy')

@patch('api.ml.strategy_trainer.joblib.dump')
@patch('api.ml.strategy_trainer.StrategyTrainer.load_strategy_class')
def test_train_agnostic_model(mock_load, mock_dump, mock_data):
    trainer = StrategyTrainer(models_dir="test_models")
    
    # Mock Strategy Instance
    mock_strategy = MagicMock()
    
    # Mock apply to return dataframe with signal & features
    def apply_side_effect(df):
        df['signal'] = 1
        df['feature1'] = 0.5
        return df
        
    mock_strategy.apply.side_effect = apply_side_effect
    mock_strategy.get_features.return_value = ['feature1']
    
    # Mock Class returning instance
    mock_load.return_value = MagicMock(return_value=mock_strategy)
    
    res = trainer.train_agnostic_model('TestStrategy', mock_data)
    
    assert res is True
    assert mock_dump.called
    # Check that model file path contains strategy name
    args, _ = mock_dump.call_args
    assert "TestStrategy.pkl" in args[1]
