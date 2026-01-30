import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from api.src.adapters.driven.exchange.ccxt_adapter import CcxtAdapter
import ccxt.async_support as ccxt

@pytest.mark.asyncio
@pytest.mark.asyncio
async def test_dynamic_exchange_default_binance():
    # Setup
    mock_db = MagicMock()
    mock_db.app_configs.find_one = AsyncMock(return_value=None)
    adapter = CcxtAdapter(db_adapter=mock_db)
    
    with patch('ccxt.async_support.binance') as mock_binance_cls:
        client = await adapter._get_system_client()
        mock_binance_cls.assert_called_once()
        assert adapter._current_exchange_id == 'binance'

@pytest.mark.asyncio
async def test_dynamic_exchange_switching_to_okx():
    # Setup
    mock_db = MagicMock()
    mock_db.app_configs.find_one = AsyncMock(return_value={"key": "active_exchange", "value": "okx"})
    adapter = CcxtAdapter(db_adapter=mock_db)
    
    # Simulate previous state
    adapter._current_exchange_id = 'binance'
    previous_instance = AsyncMock()
    adapter._exchange_instance = previous_instance
    
    # Print state before
    print(f"DEBUG: Before switch - Current: {adapter._current_exchange_id}")
    
    with patch('ccxt.async_support.okx') as mock_okx_cls:
        client = await adapter._get_system_client()
        
        print(f"DEBUG: After switch - Current: {adapter._current_exchange_id}")
        
        mock_okx_cls.assert_called_once()
        assert adapter._current_exchange_id == 'okx'
        previous_instance.close.assert_called_once()

@pytest.mark.asyncio
async def test_dynamic_exchange_caching():
    # Setup
    mock_db = MagicMock()
    mock_db.app_configs.find_one = AsyncMock(return_value={"key": "active_exchange", "value": "okx"})
    adapter = CcxtAdapter(db_adapter=mock_db)
    
    # 1. Init first time
    with patch('ccxt.async_support.okx') as mock_okx_cls:
        client1 = await adapter._get_system_client()
        # Capture the instance created
        instance_created = adapter._exchange_instance
    
    # 2. Call again - should use cache
    with patch('ccxt.async_support.okx') as mock_okx_cls_2:
        adapter._exchange_instance.close = AsyncMock()
        
        client2 = await adapter._get_system_client()
        
        mock_okx_cls_2.assert_not_called()
        assert client2 is instance_created
        adapter._exchange_instance.close.assert_not_called()

@pytest.mark.asyncio
async def test_get_historical_data_uses_dynamic_client():
    mock_db = MagicMock()
    mock_db.app_configs.find_one = AsyncMock(return_value={"key": "active_exchange", "value": "kraken"})
    
    adapter = CcxtAdapter(db_adapter=mock_db)
    
    with patch('ccxt.async_support.kraken') as mock_kraken_cls:
        mock_instance = mock_kraken_cls.return_value
        mock_instance.fetch_ohlcv = AsyncMock(return_value=[
            [1600000000000, 100, 105, 95, 102, 1000]
        ])
        
        df = await adapter.get_historical_data("BTC/USDT", "1h")
        
        assert len(df) == 1
        assert df.iloc[0]['close'] == 102
        assert adapter._current_exchange_id == 'kraken'
