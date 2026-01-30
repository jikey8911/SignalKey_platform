import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from api.src.adapters.driven.exchange.ccxt_adapter import CcxtAdapter
import ccxt.async_support as ccxt

@pytest.mark.asyncio
async def test_get_client_for_user_creates_new_instance():
    # Setup
    mock_db = MagicMock()
    adapter = CcxtAdapter(db_adapter=mock_db)
    
    user_id = "user123"
    mock_config = {
        "userId": "user123_id", 
        "activeExchange": "kraken",
        "exchanges": [{"exchangeId": "binance", "isActive": True}] 
    }
    
    # Mock get_app_config from mongo module
    with patch('api.src.adapters.driven.exchange.ccxt_adapter.get_app_config', new_callable=AsyncMock) as mock_get_config:
        mock_get_config.return_value = mock_config
        
        with patch('ccxt.async_support.kraken') as mock_kraken_cls:
             instance = await adapter._get_client_for_user(user_id)
             
             mock_get_config.assert_called_once_with(user_id)
             mock_kraken_cls.assert_called_once()
             assert adapter.user_exchange_ids[user_id] == "kraken"
             assert adapter.user_instances[user_id] == instance

@pytest.mark.asyncio
async def test_get_client_for_user_uses_cache():
    # Setup
    mock_db = MagicMock()
    adapter = CcxtAdapter(db_adapter=mock_db)
    
    user_id = "user123"
    mock_config = {"activeExchange": "kraken"}
    
    # Pre-populate cache
    existing_instance = MagicMock()
    adapter.user_instances[user_id] = existing_instance
    adapter.user_exchange_ids[user_id] = "kraken"
    
    with patch('api.src.adapters.driven.exchange.ccxt_adapter.get_app_config', new_callable=AsyncMock) as mock_get_config:
        mock_get_config.return_value = mock_config
        
        with patch('ccxt.async_support.kraken') as mock_kraken_cls:
             instance = await adapter._get_client_for_user(user_id)
             
             # Should NOT re-init
             mock_kraken_cls.assert_not_called()
             assert instance == existing_instance

@pytest.mark.asyncio
async def test_get_client_for_user_switches_exchange():
    # Setup
    mock_db = MagicMock()
    adapter = CcxtAdapter(db_adapter=mock_db)
    
    user_id = "user123"
    # User changed config to binance
    mock_config = {"activeExchange": "binance"}
    
    # Pre-populate cache as kraken
    old_instance = AsyncMock()
    adapter.user_instances[user_id] = old_instance
    adapter.user_exchange_ids[user_id] = "kraken"
    
    with patch('api.src.adapters.driven.exchange.ccxt_adapter.get_app_config', new_callable=AsyncMock) as mock_get_config:
        mock_get_config.return_value = mock_config
        
        with patch('ccxt.async_support.binance') as mock_binance_cls:
             instance = await adapter._get_client_for_user(user_id)
             
             # Should close old
             old_instance.close.assert_called_once()
             # Should init new
             mock_binance_cls.assert_called_once()
             assert adapter.user_exchange_ids[user_id] == "binance"
