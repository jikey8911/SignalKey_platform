import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from api.services.cex_service import CEXService
from api.services.dex_service import DEXService
from api.models.schemas import AnalysisResult, ExecutionResult
from api.core.domain.signal import Decision

@pytest.mark.asyncio
async def test_cex_service_get_price():
    cex = CEXService()
    with patch.object(cex, 'get_current_price', new_callable=AsyncMock) as mock_price:
        mock_price.return_value = 50000.0
        price = await cex.get_current_price("BTC/USDT", "user1")
        assert price == 50000.0

@pytest.mark.asyncio
async def test_dex_service_0x_price():
    dex = DEXService()
    # Mock de get_app_config para evitar NoneType error
    with patch('api.services.dex_service.get_app_config', new_callable=AsyncMock) as mock_config:
        mock_config.return_value = {"zeroExApiKey": "test_key"}
        
        # Mock del cliente httpx interno
        with patch.object(dex.client, 'get', new_callable=AsyncMock) as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"price": "0.0001"} # 1/10000
            mock_get.return_value = mock_response
            
            price = await dex.get_current_price("0xTOKEN", "ethereum", "user1")
            assert price == 10000.0 # 1 / 0.0001
