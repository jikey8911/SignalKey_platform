import logging
from api.infrastructure.adapters.ai_adapter import AIAdapter
from api.core.domain.signal import RawSignal, Decision
from api.models.schemas import AnalysisResult

logger = logging.getLogger(__name__)

class AIService:
    def __init__(self):
        self.adapter = AIAdapter()

    async def analyze_signal(self, text: str, config: dict = None) -> AnalysisResult:
        raw_signal = RawSignal(source="unknown", text=text)
        analysis = await self.adapter.analyze_signal(raw_signal, config)
        
        # Mapear del dominio al esquema legacy para mantener compatibilidad
        if analysis.market_type.value == "SPOT":
            market_type_legacy = "CEX"
        elif analysis.market_type.value == "FUTURES":
            market_type_legacy = "FUTURES"
        else:
            market_type_legacy = analysis.market_type.value
            
        return AnalysisResult(
            decision=analysis.decision.value,
            symbol=analysis.symbol,
            market_type=market_type_legacy,
            confidence=analysis.confidence,
            reasoning=analysis.reasoning,
            is_safe=analysis.is_safe,
            risk_score=analysis.risk_score,
            parameters={
                "entry_price": analysis.parameters.entry_price,
                "entry_type": analysis.parameters.entry_type,
                "tp": [{"price": t.price, "percent": t.percent} for t in analysis.parameters.tp],
                "sl": analysis.parameters.sl,
                "leverage": analysis.parameters.leverage,
                "amount": analysis.parameters.amount,
                "network": analysis.parameters.network
            }
        )

    async def close(self):
        """Cierra los recursos del adaptador"""
        await self.adapter.close()
