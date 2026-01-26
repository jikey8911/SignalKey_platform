import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from api.services.cex_service import CEXService
from src.domain.models.schemas import AnalysisResult
import ccxt.async_support as ccxt

@pytest.mark.asyncio
async def test_cex_service_test_connection_success():
    cex = CEXService()
    
    with patch('ccxt.async_support.binance') as mock_binance:
        instance = mock_binance.return_value
        instance.load_markets = AsyncMock()
        instance.fetch_balance = AsyncMock(return_value={'total': {'USDT': 1000}})
        instance.close = AsyncMock()
        
        success, message = await cex.test_connection('binance', 'key', 'secret')
        
        assert success is True
        assert "exitosa" in message
        instance.load_markets.assert_called_once()
        instance.fetch_balance.assert_called_once()
        instance.close.assert_called_once()

@pytest.mark.asyncio
async def test_cex_service_test_connection_failure():
    cex = CEXService()
    
    with patch('ccxt.async_support.binance') as mock_binance:
        instance = mock_binance.return_value
        instance.load_markets = AsyncMock()
        instance.fetch_balance = AsyncMock(side_effect=ccxt.AuthenticationError("Invalid API Key"))
        instance.close = AsyncMock()
        
        success, message = await cex.test_connection('binance', 'key', 'secret')
        
        assert success is False
        assert "autenticación" in message

@pytest.mark.asyncio
async def test_cex_service_get_current_price():
    cex = CEXService()
    
    mock_config = {
        "userId": "user123",
        "exchanges": [{"exchangeId": "okx", "isActive": True}]
    }
    
    with patch('api.services.cex_service.get_app_config', AsyncMock(return_value=mock_config)):
        with patch.object(cex, 'fetch_ticker_price', AsyncMock(return_value=50000.0)) as mock_fetch:
            price = await cex.get_current_price('BTC/USDT', 'user123')
            
            assert price == 50000.0
            mock_fetch.assert_called_with('BTC/USDT', 'user123', 'okx')

@pytest.mark.asyncio
async def test_cex_service_execute_trade_real_success():
    cex = CEXService()
    user_id = "user123"
    
    analysis = AnalysisResult(
        decision="BUY",
        symbol="BTC/USDT",
        market_type="SPOT",
        confidence=0.9,
        reasoning="Test",
        parameters={"amount": 0.1}
    )
    
    mock_config = {
        "userId": "obj123",
        "demoMode": False,
        "exchanges": [{"exchangeId": "binance", "apiKey": "k", "secret": "s", "isActive": True}]
    }
    
    with patch('api.services.cex_service.get_app_config', AsyncMock(return_value=mock_config)):
        with patch('ccxt.async_support.binance') as mock_binance:
            instance = mock_binance.return_value
            instance.id = 'binance'
            instance.load_markets = AsyncMock()
            instance.markets = {'BTC/USDT': {}}
            instance.symbols = ['BTC/USDT']
            instance.create_order = AsyncMock(return_value={'id': 'order987', 'status': 'open'})
            
            result = await cex.execute_trade(analysis, user_id)
            
            assert result.success is True
            assert result.order_id == 'order987'
            instance.create_order.assert_called_once()

if __name__ == "__main__":
    asyncio.run(test_cex_service_test_connection_success())
    asyncio.run(test_cex_service_test_connection_failure())
    asyncio.run(test_cex_service_get_current_price())
    asyncio.run(test_cex_service_execute_trade_real_success())
    print("All tests passed!")
