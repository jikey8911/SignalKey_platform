import google.generativeai as genai
import json
import logging
from api.config import Config
from api.models.schemas import AnalysisResult

logger = logging.getLogger(__name__)

class GeminiService:
    def __init__(self):
        if Config.GEMINI_API_KEY:
            genai.configure(api_key=Config.GEMINI_API_KEY)
            self.model = genai.GenerativeModel('gemini-1.5-flash')
        else:
            self.model = None
            logger.warning("GEMINI_API_KEY no configurado. El análisis fallará.")

    async def analyze_signal(self, text: str) -> AnalysisResult:
        if not self.model:
            return self._default_hold("API Key de Gemini no configurada")

        prompt = f"""
        Analiza la siguiente señal de trading de criptomonedas y decide si se debe realizar una operación.
        Extrae el símbolo, el tipo de mercado (SPOT o DEX), y los parámetros de la operación.
        
        Señal: "{text}"
        
        Responde ÚNICAMENTE en formato JSON con la siguiente estructura:
        {{
            "decision": "BUY" | "SELL" | "HOLD",
            "symbol": "BTC/USDT" o dirección del contrato en DEX,
            "market_type": "SPOT" | "DEX",
            "confidence": 0.0 a 1.0,
            "reasoning": "Breve explicación",
            "parameters": {{
                "amount": 0.0,
                "tp": 0.0,
                "sl": 0.0,
                "network": "solana" | "ethereum" | "bsc" (solo para DEX)
            }}
        }}
        """

        try:
            response = self.model.generate_content(prompt)
            # Limpiar la respuesta para asegurar que sea JSON válido
            content = response.text.strip()
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            
            data = json.loads(content)
            return AnalysisResult(**data)
        except Exception as e:
            logger.error(f"Error analizando señal con Gemini: {e}")
            return self._default_hold(f"Error en análisis: {str(e)}")

    def _default_hold(self, reason: str) -> AnalysisResult:
        return AnalysisResult(
            decision="HOLD",
            symbol="UNKNOWN",
            market_type="SPOT",
            confidence=0.0,
            reasoning=reason
        )
