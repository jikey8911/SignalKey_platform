import logging
from src.adapters.driven.ai.ai_adapter import AIAdapter
from src.domain.models.signal import RawSignal, Decision
from src.domain.models.schemas import AnalysisResult
from typing import List

logger = logging.getLogger(__name__)

class AIService:
    def __init__(self):
        self.adapter = AIAdapter() 
        
    async def analyze_signal(self, text: str, config: dict = None) -> List[AnalysisResult]:
        raw_signal = RawSignal(source="unknown", text=text)
        analyses = await self.adapter.analyze_signal(raw_signal, config)
        
        results = []
        for analysis in analyses:
            # Mapear del dominio al esquema legacy para mantener compatibilidad
            if analysis.market_type.value == "SPOT":
                market_type_legacy = "CEX"
            elif analysis.market_type.value == "FUTURES":
                market_type_legacy = "FUTURES"
            else:
                market_type_legacy = analysis.market_type.value
                
            results.append(AnalysisResult(
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
            ))
        return results

    async def close(self):
        """Cierra los recursos del adaptador"""
        await self.adapter.close()
