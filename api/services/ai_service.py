import json
import logging
import google.generativeai as genai
from openai import OpenAI
import requests
from api.config import Config
from api.models.schemas import AnalysisResult

logger = logging.getLogger(__name__)

class AIService:
    def __init__(self):
        self.default_model = "gemini"

    async def analyze_signal(self, text: str, config: dict = None) -> AnalysisResult:
        ai_provider = config.get("aiProvider", "gemini") if config else "gemini"
        api_key = config.get("aiApiKey") if config else None
        
        if not api_key:
            # Fallback to env vars if no user config
            if ai_provider == "gemini":
                api_key = Config.GEMINI_API_KEY
            elif ai_provider == "openai":
                api_key = getattr(Config, "OPENAI_API_KEY", None)
            elif ai_provider == "perplexity":
                api_key = getattr(Config, "PERPLEXITY_API_KEY", None)

        if not api_key:
            return self._default_hold(f"API Key para {ai_provider} no configurada")

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
            if ai_provider == "gemini":
                return await self._analyze_gemini(prompt, api_key)
            elif ai_provider == "openai":
                return await self._analyze_openai(prompt, api_key)
            elif ai_provider == "perplexity":
                return await self._analyze_perplexity(prompt, api_key)
            else:
                return self._default_hold(f"Proveedor de IA no soportado: {ai_provider}")
        except Exception as e:
            logger.error(f"Error analizando señal con {ai_provider}: {e}")
            return self._default_hold(f"Error en análisis ({ai_provider}): {str(e)}")

    async def _analyze_gemini(self, prompt: str, api_key: str) -> AnalysisResult:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-1.5-flash')
        response = model.generate_content(prompt)
        return self._parse_ai_response(response.text)

    async def _analyze_openai(self, prompt: str, api_key: str) -> AnalysisResult:
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )
        return self._parse_ai_response(response.choices[0].message.content)

    async def _analyze_perplexity(self, prompt: str, api_key: str) -> AnalysisResult:
        url = "https://api.perplexity.ai/chat/completions"
        payload = {
            "model": "llama-3.1-sonar-small-128k-online",
            "messages": [
                {"role": "system", "content": "Be precise and return only JSON."},
                {"role": "user", "content": prompt}
            ],
            "response_format": {"type": "json_object"}
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
        return self._parse_ai_response(data['choices'][0]['message']['content'])

    def _parse_ai_response(self, content: str) -> AnalysisResult:
        content = content.strip()
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
        
        data = json.loads(content)
        return AnalysisResult(**data)

    def _default_hold(self, reason: str) -> AnalysisResult:
        return AnalysisResult(
            decision="HOLD",
            symbol="UNKNOWN",
            market_type="SPOT",
            confidence=0.0,
            reasoning=reason
        )
