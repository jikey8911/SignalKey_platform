import json
import logging
from google import genai
from openai import AsyncOpenAI
import httpx
from api.core.ports.ai_port import AIPort
from api.core.domain.signal import RawSignal, SignalAnalysis, Decision, MarketType, TradingParameters, TakeProfit
from api.config import Config

logger = logging.getLogger(__name__)

class AIAdapter(AIPort):
    def __init__(self):
        self.default_model = "gemini"
        self._httpx_client = httpx.AsyncClient(timeout=60.0)

    async def close(self):
        """Cierra el cliente HTTP"""
        await self._httpx_client.aclose()

    async def analyze_signal(self, signal: RawSignal, config: dict = None) -> SignalAnalysis:
        ai_provider = config.get("aiProvider", "gemini") if config else "gemini"
        api_key = self._get_api_key(ai_provider, config)

        if not api_key:
            return self._default_hold("No API Key configured")

        prompt = self._build_prompt(signal.text)

        try:
            if ai_provider == "gemini":
                content = await self._call_gemini(prompt, api_key)
            elif ai_provider == "openai":
                content = await self._call_openai(prompt, api_key)
            elif ai_provider == "perplexity":
                content = await self._call_perplexity(prompt, api_key)
            elif ai_provider == "grok":
                content = await self._call_grok(prompt, api_key)
            else:
                return self._default_hold(f"Unsupported provider: {ai_provider}")

            return self._parse_response(content)
        except Exception as e:
            logger.error(f"Error in AI analysis: {e}")
            return self._default_hold(str(e))

    def _get_api_key(self, provider: str, config: dict) -> str:
        if config:
            key = config.get("aiApiKey") or config.get("geminiApiKey")
            if key: return key
        
        env_keys = {
            "gemini": "GEMINI_API_KEY",
            "openai": "OPENAI_API_KEY",
            "perplexity": "PERPLEXITY_API_KEY",
            "grok": "XAI_API_KEY"
        }
        return getattr(Config, env_keys.get(provider, ""), None)

    def _build_prompt(self, text: str) -> str:
        return f"""
        Analiza la siguiente señal de trading de criptomonedas y decide si se debe realizar una operación.
        Extrae el símbolo, el tipo de mercado (SPOT o DEX), y los parámetros de la operación.
        
        CRÍTICO - SEGURIDAD: 
        1. Si es un token DEX, asume que puede ser un HONEYPOT o tener baja liquidez. 
        2. Evalúa si tiene capital/liquidez suficiente para operar.
        
        Señal: "{text}"
        
        Responde ÚNICAMENTE en formato JSON con la siguiente estructura:
        {{
            "decision": "BUY" | "SELL" | "HOLD",
            "symbol": "BTC/USDT" o dirección del contrato en DEX,
            "market_type": "SPOT" | "DEX",
            "is_safe": true | false,
            "risk_score": 0.0 a 10.0,
            "confidence": 0.0 a 1.0,
            "reasoning": "Resumen de seguridad y estrategia",
            "parameters": {{
                "entry_price": 0.0,
                "entry_type": "market" | "limit",
                "tp": [
                    {{"price": 0.0, "percent": 50}},
                    {{"price": 0.0, "percent": 50}}
                ],
                "sl": 0.0,
                "leverage": 1,
                "amount": 0.0,
                "network": "solana" | "ethereum" | "bsc"
            }}
        }}
        """

    async def _call_gemini(self, prompt: str, api_key: str) -> str:
        client = genai.Client(api_key=api_key)
        response = await client.aio.models.generate_content(
            model='gemini-1.5-flash',
            contents=prompt
        )
        return response.text

    async def _call_openai(self, prompt: str, api_key: str) -> str:
        client = AsyncOpenAI(api_key=api_key)
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )
        return response.choices[0].message.content

    async def _call_perplexity(self, prompt: str, api_key: str) -> str:
        url = "https://api.perplexity.ai/chat/completions"
        payload = {
            "model": "llama-3.1-sonar-small-128k-online",
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {"type": "json_object"}
        }
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        response = await self._httpx_client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        return response.json()['choices'][0]['message']['content']

    async def _call_grok(self, prompt: str, api_key: str) -> str:
        url = "https://api.x.ai/v1/chat/completions"
        payload = {
            "model": "grok-2-1218",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0
        }
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        response = await self._httpx_client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        return response.json()['choices'][0]['message']['content']

    def _parse_response(self, content: str) -> SignalAnalysis:
        content = content.strip()
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
        
        data = json.loads(content)
        params_data = data.get("parameters", {})
        
        tp_list = [TakeProfit(price=t["price"], percent=t["percent"]) for t in params_data.get("tp", [])]
        
        params = TradingParameters(
            entry_price=params_data.get("entry_price"),
            entry_type=params_data.get("entry_type", "market"),
            tp=tp_list,
            sl=params_data.get("sl"),
            leverage=params_data.get("leverage", 1),
            amount=params_data.get("amount"),
            network=params_data.get("network")
        )

        return SignalAnalysis(
            decision=Decision(data["decision"]),
            symbol=data["symbol"],
            market_type=MarketType(data["market_type"]),
            confidence=data["confidence"],
            reasoning=data["reasoning"],
            is_safe=data.get("is_safe", True),
            risk_score=data.get("risk_score", 0.0),
            parameters=params
        )

    def _default_hold(self, reason: str) -> SignalAnalysis:
        return SignalAnalysis(
            decision=Decision.HOLD,
            symbol="UNKNOWN",
            market_type=MarketType.SPOT,
            confidence=0.0,
            reasoning=reason
        )
