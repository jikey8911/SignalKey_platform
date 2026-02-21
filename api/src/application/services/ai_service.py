import logging
import json
import re
from api.src.adapters.driven.ai.ai_adapter import AIAdapter
from api.src.domain.entities.signal import RawSignal, Decision
from api.src.domain.models.schemas import AnalysisResult
from typing import List, Dict, Any

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
                    # propagate direction so downstream adapters can build SignalAnalysis correctly
                    "direction": getattr(analysis, "direction", None).value if getattr(analysis, "direction", None) else None,
                    "entry_price": analysis.parameters.entry_price,
                    "entry_type": analysis.parameters.entry_type,
                    "tp": [{"price": t.price, "percent": t.percent, "qty": getattr(t, "qty", None), "status": getattr(t, "status", "pending")} for t in analysis.parameters.tp],
                    "sl": analysis.parameters.sl,
                    "leverage": analysis.parameters.leverage,
                    "amount": analysis.parameters.amount,
                    "investment": analysis.parameters.investment,
                    "network": analysis.parameters.network,
                }
            ))
        return results

    async def get_investment_recommendation(
        self,
        user_id: str,
        symbol: str,
        risk_level: str = "medium",
        market_type: str = "spot"
    ) -> Dict[str, Any]:
        """
        Calcula una recomendación de inversión basada en balance y riesgo.
        """
        from api.src.adapters.driven.persistence.mongodb import db, get_app_config
        
        # 1. Obtener configuración y políticas
        app_config = await get_app_config(user_id)
        wallet_policy = app_config.get("botWalletPolicy", {})
        
        # Límites globales
        min_alloc = float(wallet_policy.get("minAllocationUSDT", 10.0))
        max_alloc = float(wallet_policy.get("maxAllocationUSDT", 1000.0))
        global_pct = float(wallet_policy.get("perBotAllocationPct", 5.0))
        
        # 2. Obtener balance disponible (Simulado por defecto para seguridad)
        # TODO: Soportar balance real si market_type != simulated
        balance_doc = await db.virtual_balances.find_one({
            "userId": user_id, # user_id is passed as ObjectId or string depending on caller
            "asset": "USDT",
            "marketType": "CEX" # Asumimos CEX/Spot por ahora
        })
        
        balance_available = float(balance_doc.get("amount", 0.0)) if balance_doc else 0.0
        
        # 3. Calcular base según riesgo
        risk_factors = {
            "low": 0.02,    # 2% del balance
            "medium": 0.05, # 5% del balance
            "high": 0.10,   # 10% del balance
            "degen": 0.20   # 20% (solo para valientes)
        }
        
        factor = risk_factors.get(risk_level.lower(), 0.05)
        
        # Si hay policy global definida, usarla como base (medium)
        if global_pct > 0:
            base_pct = global_pct / 100.0
            # Ajustar según riesgo relativo a la política
            if risk_level == "low": factor = base_pct * 0.5
            elif risk_level == "high": factor = base_pct * 2.0
            else: factor = base_pct

        raw_amount = balance_available * factor
        
        # 4. Aplicar límites (Clamp)
        final_amount = max(min_alloc, min(raw_amount, max_alloc))
        
        # Guardrail final: No puede exceder el balance disponible
        final_amount = min(final_amount, balance_available)
        
        # 5. Generar razonamiento
        reasoning = (
            f"Based on your {risk_level} risk profile and available balance (${balance_available:.2f}), "
            f"we recommend allocating ${final_amount:.2f}. "
            f"This represents {((final_amount/balance_available)*100):.1f}% of your total capital, "
            f"keeping you within safe limits (Min: ${min_alloc}, Max: ${max_alloc})."
        )
        
        return {
            "symbol": symbol,
            "recommended_amount": round(final_amount, 2),
            "min_amount": min_alloc,
            "max_safe_amount": round(min(balance_available * 0.2, max_alloc), 2),
            "balance_used_pct": round((final_amount / balance_available) * 100, 2) if balance_available > 0 else 0,
            "risk_level": risk_level,
            "reasoning": reasoning
        }

    async def optimize_strategy_code(
        self,
        source_code: str,
        metrics: dict,
        trades_summary: dict,
        config: dict,
        feedback: str = None
    ) -> Dict[str, Any]:
        """
        Genera una versión optimizada de una estrategia de trading.
        """
        prompt = f"""
        ACT AS: Senior Quantitative Developer & Python Expert.

        TASK: Optimize the provided Python Trading Strategy to improve PnL and reduce Drawdown.

        CONTEXT:
        The strategy was backtested and produced the following results:
        - Win Rate: {metrics.get('win_rate')}%
        - Profit: {metrics.get('profit_pct')}%
        - Max Drawdown: {metrics.get('max_drawdown', 'N/A')}%
        - Total Trades: {metrics.get('total_trades')}

        TRADE ANALYSIS:
        - Worst Losses occurred when: {trades_summary['worst_losses']}
        - Best Wins occurred when: {trades_summary['best_wins']}

        USER FEEDBACK: {feedback if feedback else "Maximize profit while keeping risk low."}

        CURRENT CODE:
        ```python
        {source_code}
        ```

        INSTRUCTIONS:
        1. Analyze the `next()` or `apply()` logic.
        2. Identify why the losing trades happened (e.g., buying in downtrend, no stop loss).
        3. Add filters (e.g., EMA trend check, RSI bounds, Volatility filter).
        4. RETURN JSON format with:
           - "analysis": Brief explanation of flaws.
           - "modifications": List of changes made.
           - "expected_profit_pct": Estimated profit % after optimization (best effort, may be approximate)
           - "expected_win_rate": Estimated win rate % after optimization (best effort, may be approximate)
           - "code": The FULL valid Python code of the new strategy class.

        RESPONSE FORMAT (JSON ONLY):
        {{
            "analysis": "...",
            "modifications": ["..."],
            "expected_profit_pct": 0.0,
            "expected_win_rate": 0.0,
            "code": "..."
        }}
        """

        try:
            response_text = await self.adapter.generate_content(prompt, config=config)

            # Limpieza si la IA devuelve Markdown ```json ... ```
            clean_text = response_text.strip()
            if "```json" in clean_text:
                 match = re.search(r'```json\s*(.*?)\s*```', clean_text, re.DOTALL)
                 if match:
                     clean_text = match.group(1)
            elif "```" in clean_text:
                 match = re.search(r'```\s*(.*?)\s*```', clean_text, re.DOTALL)
                 if match:
                     clean_text = match.group(1)

            try:
                result = json.loads(clean_text)
            except:
                # Si falla JSON, intentar extraer solo el código si es posible o devolver error parcial
                json_match = re.search(r'(\{.*\})', clean_text, re.DOTALL)
                if json_match:
                    try:
                        result = json.loads(json_match.group(1))
                    except:
                         result = {
                            "analysis": "Optimization generated but format was invalid.",
                            "modifications": ["Code refactored."],
                            "code": response_text
                        }
                else:
                    result = {
                        "analysis": "Optimization generated but format was invalid.",
                        "modifications": ["Code refactored."],
                        "code": response_text
                    }

            return result

        except Exception as e:
            logger.error(f"AI Optimization error: {e}")
            return {
                "code": source_code, # Fallback al original
                "analysis": f"Error during optimization: {str(e)}",
                "modifications": []
            }

    async def close(self):
        """Cierra los recursos del adaptador"""
        await self.adapter.close()

    async def test_connection(self, provider: str, config: dict) -> bool:
        """Prueba la conexión con el proveedor de IA"""
        return await self.adapter.test_connection(provider, config)
