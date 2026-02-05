import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime, timedelta
from api.src.application.services.backtest_service import BacktestService
from api.src.infrastructure.adapters.ai.ai_adapter import AIAdapter
from api.src.domain.entities.signal import SignalAnalysis, Decision, MarketType, TradingParameters, TakeProfit


class TestBacktestWithAI:
    """Tests de integración para backtesting con IA"""
    
    @pytest.fixture
    def mock_ai_adapter(self):
        """Mock del AIAdapter con respuestas simuladas"""
        adapter = Mock(spec=AIAdapter)
        return adapter
    
    @pytest.fixture
    def backtest_service(self, mock_ai_adapter):
        """Instancia de BacktestService con AI adapter mockeado"""
        return BacktestService(ai_adapter=mock_ai_adapter)
    
    @pytest.fixture
    def user_config(self):
        """Configuración de usuario de prueba"""
        return {
            "aiProvider": "gemini",
            "geminiApiKey": "test_api_key_123",
            "botStrategy": {
                "maxActiveBots": 5,
                "tpLevels": 3,
                "tpPercent": 2.0,
                "slPercent": 1.5,
                "sellPercentPerTP": 33.3
            }
        }
    
    @pytest.mark.asyncio
    async def test_backtest_with_mocked_gemini(self, backtest_service, mock_ai_adapter, user_config):
        """Test: Backtest con respuestas simuladas de Gemini"""
        
        # Simular respuestas de IA
        mock_signals = [
            (20, SignalAnalysis(
                decision=Decision.BUY,
                symbol="BTC/USDT",
                market_type=MarketType.SPOT,
                confidence=0.85,
                reasoning="Strong bullish momentum detected",
                is_safe=True,
                risk_score=3.5,
                parameters=TradingParameters(
                    entry_price=45000,
                    entry_type="market",
                    tp=[
                        TakeProfit(price=46000, percent=33.3),
                        TakeProfit(price=47000, percent=33.3),
                        TakeProfit(price=48000, percent=33.4)
                    ],
                    sl=44000,
                    leverage=1,
                    amount=100,
                    network="unknown"
                )
            )),
            (50, SignalAnalysis(
                decision=Decision.SELL,
                symbol="BTC/USDT",
                market_type=MarketType.SPOT,
                confidence=0.75,
                reasoning="Taking profit at resistance",
                is_safe=True,
                risk_score=2.0,
                parameters=TradingParameters(
                    entry_price=46500,
                    entry_type="market",
                    tp=[],
                    sl=47000,
                    leverage=1,
                    amount=0,
                    network="unknown"
                )
            ))
        ]
        
        mock_ai_adapter.analyze_historical_batch = AsyncMock(return_value=mock_signals)
        
        # Ejecutar backtest
        result = await backtest_service.run_backtest(
            symbol="BTC/USDT",
            days=3,
            timeframe="1h",
            use_ai=True,
            user_config=user_config
        )
        
        # Validaciones
        assert result["strategy_used"] == "ai"
        assert result["symbol"] == "BTC/USDT"
        assert result["total_trades"] >= 1
        assert "ai_confidence_avg" in result
        assert result["ai_confidence_avg"] > 0
        assert result["ai_decisions_count"] == 2
        assert "max_drawdown" in result
        assert "equity_curve" in result
    
    @pytest.mark.asyncio
    async def test_backtest_sma_strategy(self, backtest_service):
        """Test: Backtest con estrategia SMA (sin IA)"""
        
        result = await backtest_service.run_backtest(
            symbol="BTC/USDT",
            days=3,
            timeframe="1h",
            use_ai=False,
            user_config=None
        )
        
        # Validaciones
        assert result["strategy_used"] == "sma"
        assert result["symbol"] == "BTC/USDT"
        assert "total_trades" in result
        assert "profit_percentage" in result
        assert "ai_confidence_avg" not in result  # No debe tener métricas de IA
    
    @pytest.mark.asyncio
    async def test_backtest_failover_providers(self, backtest_service, mock_ai_adapter, user_config):
        """Test: Failover entre proveedores de IA"""
        
        # Simular que Gemini falla pero OpenAI funciona
        async def mock_batch_with_failover(*args, **kwargs):
            # Primera llamada falla (Gemini)
            if not hasattr(mock_batch_with_failover, 'called'):
                mock_batch_with_failover.called = True
                raise Exception("Gemini API error")
            # Segunda llamada funciona (OpenAI)
            return [(30, SignalAnalysis(
                decision=Decision.BUY,
                symbol="BTC/USDT",
                market_type=MarketType.SPOT,
                confidence=0.80,
                reasoning="Bullish pattern",
                is_safe=True,
                risk_score=4.0,
                parameters=TradingParameters(
                    entry_price=45000,
                    entry_type="market",
                    tp=[TakeProfit(price=46000, percent=100)],
                    sl=44000,
                    leverage=1,
                    amount=100,
                    network="unknown"
                )
            ))]
        
        mock_ai_adapter.analyze_historical_batch = mock_batch_with_failover
        
        # Configurar múltiples proveedores
        user_config["openaiApiKey"] = "test_openai_key"
        
        result = await backtest_service.run_backtest(
            symbol="BTC/USDT",
            days=3,
            timeframe="1h",
            use_ai=True,
            user_config=user_config
        )
        
        # Debe completarse exitosamente con el proveedor de respaldo
        assert result["strategy_used"] == "ai"
        assert "error" not in result
    
    @pytest.mark.asyncio
    async def test_backtest_metrics_calculation(self, backtest_service, mock_ai_adapter, user_config):
        """Test: Validar cálculos de métricas"""
        
        # Simular trades con P&L conocido
        mock_signals = [
            (10, SignalAnalysis(
                decision=Decision.BUY,
                symbol="BTC/USDT",
                market_type=MarketType.SPOT,
                confidence=0.90,
                reasoning="Entry signal",
                is_safe=True,
                risk_score=2.0,
                parameters=TradingParameters(
                    entry_price=100,
                    entry_type="market",
                    tp=[TakeProfit(price=110, percent=100)],
                    sl=95,
                    leverage=1,
                    amount=100,
                    network="unknown"
                )
            )),
            (20, SignalAnalysis(
                decision=Decision.SELL,
                symbol="BTC/USDT",
                market_type=MarketType.SPOT,
                confidence=0.85,
                reasoning="Exit signal",
                is_safe=True,
                risk_score=2.0,
                parameters=TradingParameters(
                    entry_price=110,
                    entry_type="market",
                    tp=[],
                    sl=0,
                    leverage=1,
                    amount=0,
                    network="unknown"
                )
            ))
        ]
        
        mock_ai_adapter.analyze_historical_batch = AsyncMock(return_value=mock_signals)
        
        result = await backtest_service.run_backtest(
            symbol="BTC/USDT",
            days=3,
            timeframe="1h",
            use_ai=True,
            user_config=user_config
        )
        
        # Validar métricas
        assert result["total_trades"] == 1
        assert result["winning_trades"] >= 0
        assert result["losing_trades"] >= 0
        assert result["win_rate"] >= 0 and result["win_rate"] <= 100
        assert result["max_drawdown"] >= 0
        assert len(result["equity_curve"]) > 0
    
    @pytest.mark.asyncio
    async def test_backtest_no_api_key(self, backtest_service):
        """Test: Backtest sin API key configurada debe fallar"""
        
        result = await backtest_service.run_backtest(
            symbol="BTC/USDT",
            days=3,
            timeframe="1h",
            use_ai=True,
            user_config={}  # Sin API keys
        )
        
        # Debe retornar error o usar estrategia de respaldo
        # (dependiendo de la implementación)
        assert "error" in result or result["strategy_used"] == "sma"
    
    @pytest.mark.asyncio
    async def test_backtest_empty_signals(self, backtest_service, mock_ai_adapter, user_config):
        """Test: Backtest cuando la IA no genera señales"""
        
        # Simular que la IA no genera señales (solo HOLD)
        mock_ai_adapter.analyze_historical_batch = AsyncMock(return_value=[])
        
        result = await backtest_service.run_backtest(
            symbol="BTC/USDT",
            days=3,
            timeframe="1h",
            use_ai=True,
            user_config=user_config
        )
        
        # Debe completarse sin trades
        assert result["total_trades"] == 0
        assert result["profit_percentage"] == 0
        assert result["ai_decisions_count"] == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
