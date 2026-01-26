from typing import List, Dict, Any
from src.domain.entities.signal import SignalAnalysis, MarketType, Decision, TradingParameters, TakeProfit
from src.domain.ports.output.ai_port import IAIPort
from src.application.services.ai_service import AIService # Reutilizamos el servicio existente envolviéndolo

class AIAdapter(IAIPort):
    def __init__(self, ai_service: AIService):
        self.ai_service = ai_service

    async def analyze_signal(self, text: str, config: Dict[str, Any]) -> List[SignalAnalysis]:
        # Llamamos al servicio original que ya tiene la lógica de prompts y LLM
        analyses = await self.ai_service.analyze_signal(text, config)
        
        # Mapeamos los resultados del servicio original a nuestras entidades de dominio
        # (En este caso el servicio original ya usaba dataclasses similares, pero aseguramos el desacoplamiento)
        domain_analyses = []
        for a in analyses:
            # Mapeo de parámetros de trading
            params = TradingParameters(
                entry_price=a.parameters.entry_price,
                entry_type=a.parameters.entry_type,
                tp=[TakeProfit(price=tp.price, percent=tp.percent) for tp in a.parameters.tp],
                sl=a.parameters.sl,
                leverage=a.parameters.leverage,
                amount=a.parameters.amount,
                network=a.parameters.network
            )
            
            domain_analyses.append(SignalAnalysis(
                decision=Decision(a.decision),
                symbol=a.symbol,
                market_type=MarketType(a.market_type),
                confidence=a.confidence,
                reasoning=a.reasoning,
                is_safe=a.is_safe,
                risk_score=a.risk_score,
                parameters=params
            ))
        return domain_analyses
