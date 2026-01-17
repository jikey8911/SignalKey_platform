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
        # Log del config recibido (sin exponer las keys completas)
        if config:
            config_keys = list(config.keys())
            logger.info(f"Analyzing signal with config keys: {config_keys}")
        else:
            logger.info("Analyzing signal with no config provided")
        
        # Leer el proveedor seleccionado
        ai_provider = config.get("aiProvider", "gemini") if config else "gemini"
        logger.info(f"Selected AI provider: {ai_provider}")
        
        # Leer la API key con fallback a campo legacy
        api_key = None
        if config:
            api_key = config.get("aiApiKey")
            
            # Fallback a campo legacy si no existe aiApiKey
            if not api_key and ai_provider == "gemini":
                api_key = config.get("geminiApiKey")
                if api_key:
                    logger.warning("Using legacy 'geminiApiKey' field. Please update config to use 'aiApiKey'")
        
        # Si aún no hay API key, usar variables de entorno
        if not api_key:
            logger.warning(f"No API key found in config for {ai_provider}, falling back to environment variables")
            if ai_provider == "gemini":
                api_key = Config.GEMINI_API_KEY
            elif ai_provider == "openai":
                api_key = getattr(Config, "OPENAI_API_KEY", None)
            elif ai_provider == "perplexity":
                api_key = getattr(Config, "PERPLEXITY_API_KEY", None)

        # Validar que tenemos una API key
        if not api_key:
            error_msg = f"No API Key configured for {ai_provider}. Please configure it in Settings."
            logger.error(error_msg)
            return self._default_hold(error_msg)
        
        logger.info(f"API key found for {ai_provider} (length: {len(api_key) if api_key else 0})")

        prompt = f"""
        Analiza la siguiente señal de trading de criptomonedas y decide si se debe realizar una operación.
        Extrae el símbolo, el tipo de mercado (SPOT o DEX), y los parámetros de la operación.
        
        CRÍTICO - SEGURIDAD: 
        1. Si es un token DEX, asume que puede ser un HONEYPOT o tener baja liquidez. 
        2. Intenta validar si el token es seguro basándote en la información del texto o el contexto del canal.
        3. Evalúa si tiene capital/liquidez suficiente para operar.
        
        Señal: "{text}"
        
        Responde ÚNICAMENTE en formato JSON con la siguiente estructura:
        {{
            "decision": "BUY" | "SELL" | "HOLD",
            "symbol": "BTC/USDT" o dirección del contrato en DEX,
            "market_type": "SPOT" | "DEX",
            "is_safe": true | false,
            "risk_score": 0.0 (seguro) a 10.0 (peligroso),
            "confidence": 0.0 a 1.0,
            "reasoning": "Resumen de seguridad y estrategia",
            "parameters": {{
                "entry_price": 0.0 (precio objetivo si es limit, o null si es mercado),
                "entry_type": "market" | "limit",
                "tp": [
                    {{"price": 0.0, "percent": 50}}, // Lista de Take Profits con porcentaje a vender
                    {{"price": 0.0, "percent": 50}}
                ],
                "sl": 0.0,
                "leverage": 1, // Para CEX Futuros
                "amount": 0.0, // Monto sugerido (opcional)
                "network": "solana" | "ethereum" | "bsc" (solo para DEX)
            }}
        }}
        """

        try:
            logger.info(f"Calling {ai_provider} API for signal analysis...")
            result = None
            
            if ai_provider == "gemini":
                result = await self._analyze_gemini(prompt, api_key)
            elif ai_provider == "openai":
                result = await self._analyze_openai(prompt, api_key)
            elif ai_provider == "perplexity":
                result = await self._analyze_perplexity(prompt, api_key)
            else:
                error_msg = f"Proveedor de IA no soportado: {ai_provider}"
                logger.error(error_msg)
                return self._default_hold(error_msg)
            
            logger.info(f"AI analysis completed with {ai_provider}: decision={result.decision}, symbol={result.symbol}, confidence={result.confidence}")
            return result
            
        except Exception as e:
            logger.error(f"Error analizando señal con {ai_provider}: {e}", exc_info=True)
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
