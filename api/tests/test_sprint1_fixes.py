
import pytest
import pandas as pd
from unittest.mock import MagicMock, AsyncMock, patch
from api.src.domain.strategies.base import BaseStrategy
from api.src.application.services.execution_engine import ExecutionEngine
from api.src.application.services.simulation_service import SimulationService
from api.src.domain.services.strategy_trainer import StrategyTrainer
from api.src.application.services.ml_service import MLService

# --- Mocks & Fixtures ---

class CustomFeatureStrategy(BaseStrategy):
    """Estrategia dummy para probar get_features"""
    def apply(self, df: pd.DataFrame) -> pd.DataFrame:
        df['custom_metric'] = df['close'] * 2
        df['signal'] = BaseStrategy.SIGNAL_WAIT
        return df
    
    def get_features(self):
        return ['custom_metric', 'close'] # Non-standard features

class LegacyStrategy(BaseStrategy):
    """Estrategia que falla al no devolver features (simulando contrato roto)"""
    def apply(self, df: pd.DataFrame) -> pd.DataFrame:
        return df
    
    def get_features(self):
        return [] # Empty list should trigger error

@pytest.fixture
def mock_db():
    return MagicMock()

@pytest.fixture
def mock_exchange():
    return MagicMock()

# --- Tests ---

@pytest.mark.asyncio
async def test_execution_engine_uses_constants(mock_db):
    """Verifica que ExecutionEngine usa SIGNAL_BUY/SELL en lugar de 1/2"""
    engine = ExecutionEngine(mock_db)
    engine.simulator = AsyncMock() # Mock simulator to check calls
    engine.socket = AsyncMock()
    
    # Mock finding updated config
    mock_db.db.__getitem__.return_value.find_one = AsyncMock(return_value={"value": 100}) 
    
    # Configure simulator to return a concrete dict
    engine.simulator.execute_trade.return_value = {"status": "executed", "pnl": 50.0} 
    
    # Case 1: BUY Signal
    buy_signal = {'signal': BaseStrategy.SIGNAL_BUY, 'price': 50000}
    bot_instance = {'id': '507f1f77bcf86cd799439011', 'status': 'active', 'mode': 'simulated', 'symbol': 'BTC/USDT', 'position': {'qty':0, 'avg_price':0}}
    
    await engine.process_signal(bot_instance, buy_signal)
    
    # Verificar que se llamó al simulador con SIGNAL_BUY
    engine.simulator.execute_trade.assert_called_with(bot_instance, BaseStrategy.SIGNAL_BUY, 50000, 100)

@pytest.mark.asyncio
async def test_simulation_service_uses_constants(mock_db):
    """Verifica que SimulationService entiende SIGNAL_BUY/SELL"""
    sim = SimulationService(mock_db)
    sim.db.db.__getitem__.return_value.insert_one = AsyncMock() # Mock insert
    sim.db.db.__getitem__.return_value.update_one = AsyncMock() # Mock update
    
    bot_instance = {'id': '507f1f77bcf86cd799439011', 'symbol': 'BTC/USDT', 'position': {'qty': 1, 'avg_price': 40000}}
    
    # Test BUY
    await sim.execute_trade(bot_instance, BaseStrategy.SIGNAL_BUY, 50000, 1000)
    args, _ = sim.db.db["simulation_trades"].insert_one.call_args
    assert args[0]['side'] == 'buy'
    
    # Test SELL
    await sim.execute_trade(bot_instance, BaseStrategy.SIGNAL_SELL, 55000, 1000)
    args, _ = sim.db.db["simulation_trades"].insert_one.call_args
    assert args[0]['side'] == 'sell'

@pytest.mark.asyncio
async def test_strategy_trainer_enforces_get_features():
    """Verifica que el entrenador falle si la estrategia no devuelve features válidos"""
    trainer = StrategyTrainer()
    
    # Mock dynamic loading to return our dummy strategy
    trainer.load_strategy_class = MagicMock(return_value=LegacyStrategy)
    
    # Dummy data
    data = {'BTC/USDT': pd.DataFrame({'close': [10, 11, 12]})}
    
    result = await trainer.train_agnostic_model('LegacyStrategy', data)
    assert result is False, "El entrenador debería fallar si get_features devuelve lista vacía"

@pytest.mark.asyncio
async def test_ml_service_respects_contract(mock_exchange):
    """Verifica MLService usa features de la estrategia"""
    service = MLService(mock_exchange)
    service.trainer.load_strategy_class = MagicMock(return_value=CustomFeatureStrategy)
    
    # Mock joblib load to return a fake model
    fake_model.predict.return_value = [1, 1] # Predict BUY for 2 rows
    
    with patch('api.src.application.services.ml_service.joblib.load', return_value=fake_model), \
         patch('api.src.application.services.ml_service.os.path.exists', return_value=True):
         # Data with missing custom feature
         data_missing = {'BTC/USDT': pd.DataFrame({'close': [100, 101], 'other': [1,2]})}
         
         # MOCK TRAINER
         service.trainer = MagicMock()
         service.trainer.load_strategy_class.return_value = CustomFeatureStrategy

         result = await service._run_strategy_backtest("CustomStrategy", data_missing)
         
         # If successful, result is a dict. If failed (e.g. strict feature check failed), None.
         # In this case, CustomFeatureStrategy().apply() ADDS 'custom_metric', so it should succeed.
         assert result is not None
         assert result['name'] == "CustomStrategy"
