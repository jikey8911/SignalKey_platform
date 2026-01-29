import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from api.src.application.services.simulation_service import SimulationService
from api.src.application.services.execution_engine import ExecutionEngine
from datetime import datetime

from bson import ObjectId

# Tests for SimulationService
@pytest.mark.asyncio
async def test_simulation_trade():
    mock_db = MagicMock()
    mock_collection = AsyncMock()
    mock_db.db.__getitem__.return_value = mock_collection
    
    service = SimulationService(mock_db)
    
    bot_instance = {
        'id': str(ObjectId()),
        'symbol': 'BTC/USDT',
        'position': {'qty': 0, 'avg_price': 0},
        'mode': 'simulated'
    }
    
    # Buy signal
    result = await service.execute_trade(bot_instance, 1, 50000, 100)
    
    assert result['side'] == 'buy'
    assert result['price'] == 50000
    assert result['amount'] == 100
    
    # Verify update called
    mock_collection.update_one.assert_called_once()
    mock_collection.insert_one.assert_called_once()


# Tests for ExecutionEngine
@pytest.mark.asyncio
async def test_engine_process_signal_simulated():
    mock_db = MagicMock()
    mock_collection = AsyncMock()
    mock_db.db.__getitem__.return_value = mock_collection
    mock_collection.find_one.return_value = {"investmentAmount": 20.0} # mock app_config

    engine = ExecutionEngine(mock_db)
    # Mock simulator
    engine.simulator.execute_trade = AsyncMock(return_value={"status": "simulated_ok"})
    
    bot_instance = {
        'id': 'bot1',
        'symbol': 'BTC/USDT',
        'status': 'active',
        'mode': 'simulated',
         'user_id': 'u1'
    }
    
    # Process
    result = await engine.process_signal(bot_instance, {'signal': 1, 'price': 50000})
    
    assert result == {"status": "simulated_ok"}
    engine.simulator.execute_trade.assert_called_with(bot_instance, 1, 50000, 20.0)

@pytest.mark.asyncio
async def test_engine_process_signal_skipped_paused():
    mock_db = MagicMock()
    engine = ExecutionEngine(mock_db)
    
    bot_instance = {
        'id': 'bot1',
        'status': 'paused'
    }
    
    result = await engine.process_signal(bot_instance, {'signal': 1, 'price': 50000})
    assert result['status'] == 'skipped'

