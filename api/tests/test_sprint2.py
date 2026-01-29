import pytest
import pandas as pd
import joblib
from unittest.mock import MagicMock, patch, AsyncMock
from api.src.application.services.backtest_service import BacktestService
from api.src.domain.entities.bot_instance import BotInstance
from api.src.adapters.driven.persistence.mongodb_bot_repository import MongoBotRepository
from datetime import datetime

# Tests for BotInstance
def test_bot_instance_creation():
    bot = BotInstance(
        id="123",
        user_id="user1",
        name="TestBot",
        symbol="BTC/USDT",
        strategy_name="RSI",
        timeframe="1h",
        mode="simulated",
        status="active"
    )
    assert bot.status == "active"
    assert bot.config == {}
    d = bot.to_dict()
    assert d["id"] == "123"
    assert d["symbol"] == "BTC/USDT"

# Tests for MongoBotRepository
@pytest.mark.asyncio
async def test_repo_save():
    with patch('api.src.adapters.driven.persistence.mongodb_bot_repository.AsyncIOMotorClient') as mock_client:
        mock_db = MagicMock()
        mock_collection = AsyncMock()
        mock_client.return_value.__getitem__.return_value = mock_db
        mock_db.__getitem__.return_value = mock_collection
        
        mock_collection.insert_one.return_value.inserted_id = "new_id"
        
        repo = MongoBotRepository()
        
        bot = BotInstance(
             id=None, user_id="u1", name="b1", symbol="s1", strategy_name="st1", timeframe="1h"
        )
        
        saved_id = await repo.save(bot)
        assert saved_id == "new_id"
        mock_collection.insert_one.assert_called_once()

# Tests for BacktestService
@pytest.mark.asyncio
async def test_find_best_strategy():
    mock_exchange = AsyncMock()
    # Mock data
    ohlcv = [
        [1600000000000, 100, 105, 95, 101, 1000],
        [1600003600000, 101, 106, 96, 102, 1000],
        [1600007200000, 102, 107, 97, 103, 1000], # +
        [1600010800000, 103, 108, 98, 99, 1000],  # -
    ]
    mock_exchange.get_historical_ohlcv.return_value = ohlcv
    
    with patch('api.src.application.services.backtest_service.StrategyTrainer') as MockTrainer:
        trainer_instance = MockTrainer.return_value
        trainer_instance.discover_strategies.return_value = ["TestStrat"]
        
        mock_strat_class = MagicMock()
        mock_strat_instance = MagicMock()
        # Mock features logic
        mock_strat_instance.get_features.return_value = ['close']
        
        # apply returns dataframe with features
        def apply_mock(df):
            df['feature1'] = df['close']
            return df
        mock_strat_instance.apply.side_effect = apply_mock
        
        mock_strat_class.return_value = mock_strat_instance
        trainer_instance.load_strategy_class.return_value = mock_strat_class
        
        # Mock joblib load
        with patch('api.src.application.services.backtest_service.joblib.load') as mock_load:
            mock_model = MagicMock()
            # Predict returns signals: 1 (buy), 2 (sell), 0 (hold)
            mock_model.predict.return_value = [1, 1, 1, 2] # 4 rows
            mock_load.return_value = mock_model
            
            with patch('api.src.application.services.backtest_service.os.path.exists', return_value=True):
                service = BacktestService(mock_exchange, models_dir="test_models")
                result = await service.find_best_strategy("BTC/USDT", "1h", 30)
                
                assert result['symbol'] == "BTC/USDT"
                assert result['best_strategy'] == "TestStrat"
                assert 'all_results' in result
