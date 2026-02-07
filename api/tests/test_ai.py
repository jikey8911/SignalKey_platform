import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from api.src.infrastructure.adapters.ai.ai_adapter import AIAdapter
from api.src.application.services.ai_service import AIService
from api.src.domain.entities.signal import Decision, RawSignal

@pytest.mark.asyncio
async def test_ai_adapter_analyze_signal():
    service = AIService()
    adapter = AIAdapter(ai_service=service)
    raw_signal = RawSignal(source="test", text="Buy BTC at 50000")
    
    # Mock de los modelos de IA según el proveedor
    with patch.object(service, 'analyze_signal', new_callable=AsyncMock) as mock_analyze:
        mock_analyze.return_value = [] # Simulamos una respuesta vacía
        results = await adapter.analyze_signal("Buy BTC at 50000", {"aiProvider": "gemini"})
        assert results == []
        mock_analyze.assert_called_once()

@pytest.mark.asyncio
async def test_ai_service_analyze_signal():
    service = AIService()
    text = "Signal: BUY SOL"
    
    # Mock del adaptador
    with patch.object(service.adapter, 'analyze_signal', new_callable=AsyncMock) as mock_analyze:
        from api.src.domain.entities.signal import SignalAnalysis, Decision, MarketType
        mock_result = SignalAnalysis(
            decision=Decision.BUY,
            symbol="SOLUSDT",
            market_type=MarketType.CEX,
            confidence=0.9,
            reasoning="Test"
        )
        mock_analyze.return_value = [mock_result]
        
        results = await service.analyze_signal(text)
        assert len(results) == 1
        assert results[0].decision == "BUY"
        assert results[0].symbol == "SOLUSDT"
