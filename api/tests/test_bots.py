import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from api.src.infrastructure.telegram.telegram_bot import TelegramUserBot
from api.src.application.services.bot_service import SignalBotService
from api.src.domain.models.schemas import AnalysisResult
from api.src.domain.entities.signal import Decision

@pytest.mark.asyncio
async def test_telegram_bot_init():
    with patch('telethon.TelegramClient'):
        bot = TelegramUserBot("user1", "api_id", "api_hash")
        assert bot.user_id == "user1"
        assert bot.client is None

@pytest.mark.asyncio
async def test_signal_bot_service_activation():
    mock_cex = MagicMock()
    mock_cex._normalize_symbol.return_value = "BTC/USDT"
    mock_cex.get_current_price = AsyncMock(return_value=50000.0)
    mock_cex.execute_trade = AsyncMock(return_value=MagicMock(success=True, order_id="12345", message="Success BTC/USDT"))
    
    mock_dex = MagicMock()
    
    service = SignalBotService(cex_service=mock_cex, dex_service=mock_dex)
    
    analysis = MagicMock()
    analysis.symbol = "BTCUSDT"
    analysis.decision = "BUY"
    analysis.market_type = "CEX"
    analysis.confidence = 0.9
    analysis.reasoning = "Test Signal"
    analysis.parameters = {"amount": 100}
    
    mock_db = MagicMock()
    mock_db.trades.count_documents = AsyncMock(return_value=0)
    mock_db.trades.find_one = AsyncMock(return_value=None)
    
    with patch('api.src.application.services.bot_service.db', mock_db):
        with patch('api.src.application.services.bot_service.save_trade', new_callable=AsyncMock):
             config = {
                 "demoMode": True, 
                 "_id": "user_id",
                 "botStrategy": {"maxActiveBots": 5, "tpLevels": 3, "tpPercent": 2.0, "slPercent": 1.5}
             }
             result = await service.activate_bot(analysis, "user1", config)
             assert result.success is True
             assert "BTC/USDT" in result.message
