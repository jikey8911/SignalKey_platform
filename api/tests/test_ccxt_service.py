import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import ccxt.async_support as ccxt
from api.services.ccxt_service import CCXTService

@pytest.mark.asyncio
async def test_ccxt_service_create_public_instance():
    service = CCXTService()
    
    with patch('ccxt.async_support.binance') as mock_binance:
        instance = await service.create_public_instance('binance')
        assert instance is not None
        assert 'binance' in service.public_instances
        
        # Second call should return cached instance
        instance2 = await service.create_public_instance('binance')
        assert instance is instance2
        mock_binance.assert_called_once()

@pytest.mark.asyncio
async def test_ccxt_service_test_connection_private_success():
    service = CCXTService()
    
    with patch('ccxt.async_support.binance') as mock_binance:
        instance = mock_binance.return_value
        instance.load_markets = AsyncMock()
        instance.fetch_balance = AsyncMock(return_value={'total': {'USDT': 1000}})
        instance.close = AsyncMock()
        
        success, message = await service.test_connection_private('binance', 'key', 'secret')
        
        assert success is True
        assert "exitosa" in message
        instance.load_markets.assert_called_once()
        instance.fetch_balance.assert_called_once()
        instance.close.assert_called_once()

@pytest.mark.asyncio
async def test_ccxt_service_fetch_balance_private():
    service = CCXTService()
    
    with patch('ccxt.async_support.okx') as mock_okx:
        instance = mock_okx.return_value
        instance.fetch_balance = AsyncMock(return_value={'total': {'USDT': 500}})
        instance.close = AsyncMock()
        
        balance = await service.fetch_balance_private('okx', 'key', 'secret', 'pass')
        
        assert balance['total']['USDT'] == 500
        # Verify OKX specific params
        instance.fetch_balance.assert_called_once_with(params={'type': 'spot'})
        instance.close.assert_called_once()

if __name__ == "__main__":
    asyncio.run(test_ccxt_service_create_public_instance())
    asyncio.run(test_ccxt_service_test_connection_private_success())
    asyncio.run(test_ccxt_service_fetch_balance_private())
    print("CCXTService tests passed!")
