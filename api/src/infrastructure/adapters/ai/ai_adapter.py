from typing import List, Dict, Any
from api.src.domain.entities.signal import SignalAnalysis, MarketType, Decision, Direction, TradingParameters, TakeProfit
from api.src.domain.ports.output.ai_port import IAIPort
from api.src.application.services.ai_service import AIService # Reutilizamos el servicio existente envolviéndolo

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
            # `AnalysisResult.parameters` is a dict (legacy). Map defensively.
            p = a.parameters or {}

            tp_items = []
            for t in (p.get("tp") or []):
                if not isinstance(t, dict):
                    continue

                price_val = t.get("price")
                percent_val = t.get("percent")
                if price_val is None or percent_val is None:
                    # e.g. "TP2: dejar correr" can come without a numeric price
                    continue

                tp_items.append(
                    TakeProfit(
                        price=float(price_val),
                        percent=float(percent_val),
                        qty=t.get("qty"),
                        status=t.get("status", "pending"),
                    )
                )

            params = TradingParameters(
                entry_price=p.get("entry_price"),
                entry_type=p.get("entry_type", "market"),
                tp=tp_items,
                sl=p.get("sl"),
                leverage=p.get("leverage", 1),
                amount=p.get("amount"),
                investment=p.get("investment"),
                network=p.get("network"),
            )

            # decision/direction values
            decision_val = a.decision
            direction_val = p.get("direction") or getattr(a, "direction", None) or getattr(a, "side", None) or "HOLD"

            domain_analyses.append(
                SignalAnalysis(
                    decision=Decision(decision_val) if decision_val in [d.value for d in Decision] else Decision.APPROVED,
                    direction=Direction(direction_val) if direction_val in [d.value for d in Direction] else Direction.HOLD,
                    symbol=a.symbol,
                    market_type=MarketType(a.market_type) if a.market_type in [m.value for m in MarketType] else MarketType.SPOT,
                    confidence=a.confidence,
                    reasoning=a.reasoning,
                    is_safe=a.is_safe,
                    risk_score=a.risk_score,
                    parameters=params,
                )
            )
        return domain_analyses
