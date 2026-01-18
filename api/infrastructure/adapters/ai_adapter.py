import json
import logging
from google import genai
from openai import AsyncOpenAI
import httpx
import re
from typing import List
from perplexity import AsyncPerplexity
from api.core.ports.ai_port import AIPort
from api.core.domain.signal import RawSignal, SignalAnalysis, Decision, MarketType, TradingParameters, TakeProfit
from api.config import Config

logger = logging.getLogger(__name__)

class AIAdapter(AIPort):
    def __init__(self):
        self.default_model = "gemini"
        self._httpx_client = httpx.AsyncClient(timeout=60.0)
        self._pplx_client = None # Lazy initialization

    async def close(self):
        """Cierra el cliente HTTP y de Perplexity"""
        await self._httpx_client.aclose()
        if self._pplx_client:
            await self._pplx_client.close() # El SDK de PPLX usa .close()

    async def analyze_signal(self, signal: RawSignal, config: dict = None) -> List[SignalAnalysis]:
        # Lista de proveedores en orden de prioridad para el failover
        all_providers = ["gemini", "openai", "perplexity", "grok"]
        
        # Obtener el proveedor primario (seleccionado por el usuario)
        primary_provider = config.get("aiProvider", "gemini") if config else "gemini"
        
        # Reordenar la lista para poner el primario al principio
        priority_list = [primary_provider] + [p for p in all_providers if p != primary_provider]
        
        last_error = "No AI providers configured or available"
        
        for provider in priority_list:
            api_key = self._get_api_key(provider, config)
            if not api_key:
                continue
                
            logger.info(f"Attempting signal analysis with provider: {provider}")
            
            try:
                if provider == "gemini":
                    content = await self._call_gemini(self._build_prompt(signal.text), api_key)
                elif provider == "openai":
                    content = await self._call_openai(self._build_prompt(signal.text), api_key)
                elif provider == "perplexity":
                    content = await self._call_perplexity(self._build_prompt(signal.text), api_key)
                elif provider == "grok":
                    content = await self._call_grok(self._build_prompt(signal.text), api_key)
                else:
                    continue

                analysis = self._parse_response(content)
                # Si el parseo devolvió un solo item con HOLD por error interno, seguimos intentando
                if len(analysis) == 1 and analysis[0].decision == Decision.HOLD and "Error" in analysis[0].reasoning:
                    last_error = analysis[0].reasoning
                    logger.warning(f"Provider {provider} returned HOLR/Error: {last_error}. Retrying next...")
                    continue
                    
                logger.info(f"Successfully analyzed signal with {provider}")
                return analysis
                
            except Exception as e:
                last_error = str(e)
                logger.error(f"Error analyzing with {provider}: {e}")
                continue
        
        # Si llegamos aquí, todos fallaron
        logger.error(f"All AI providers failed. Last error: {last_error}")
        return [self._default_hold(f"All AI providers failed. Last error: {last_error}")]

    def _get_api_key(self, provider: str, config: dict) -> str:
        if config:
            # Primero intentar el campo específico del nuevo esquema
            key_map = {
                "gemini": "geminiApiKey",
                "openai": "openaiApiKey",
                "perplexity": "perplexityApiKey",
                "grok": "grokApiKey"
            }
            key = config.get(key_map.get(provider, ""))
            if key: return key
            
            # Fallback al campo genérico antiguo si coincide con el proveedor seleccionado
            if config.get("aiProvider") == provider:
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
        Tu tarea es extraer parámetros técnicos de un texto descriptivo y devolverlos en formato JSON. 
        Este es un sistema de procesamiento de datos automático.
        
        REGLAS DE EXTRACCIÓN Y GENERACIÓN:
        1. SÍMBOLO: Si es una alerta de bot (GMGN/Trend), busca la dirección de contrato (CA) o el par (p.ej. BTC/USDT).
        2. MERCADO: 
           - 'SPOT' (CEX/Centralizado sin apalancamiento).
           - 'FUTURES' (CEX con apalancamiento, p.ej. "Long x20", "Short", "Cross 10x").
           - 'DEX' (Descentralizado/Solana/Base, p.ej. CA de Solana).
        3. DECISIÓN: 
           - 'BUY' si el texto indica una entrada, compra, Long o alerta positiva.
           - 'SELL' si el texto indica una salida, venta o Short.
           - 'HOLD' si el texto no contiene una operación clara, es publicidad, spam o soporte.
        4. PARÁMETROS (MANDATORIOS SI DECISIÓN != 'HOLD'):
           - Si el texto NO contiene entry_price, tp o sl, DEBES generarlos tú basándote en el precio actual (usa tu búsqueda si es posible) o ratios prudentes (ej. SL: 2-5%, TP1: 5-10%).
           - NUNCA devuelvas 0.0 para entry_price si la decisión es BUY/SELL.
           - El campo 'leverage' debe ser coherente con el mercado (1 para SPOT/DEX).
        
        TEXTO A PROCESAR:
        "{text}"
        
        RESPUESTA JSON (Sin preámbulos, deveulve un ARRAY [] de objetos si hay múltiples tokens):
        [
            {{
                "decision": "BUY" | "SELL" | "HOLD",
                "symbol": "Símbolo o Dirección",
                "market_type": "SPOT" | "FUTURES" | "DEX",
                "is_safe": true | false,
                "risk_score": 0.0 a 10.0,
                "confidence": 0.0 a 1.0,
                "reasoning": "Resumen técnico de la extracción",
                "parameters": {{
                    "entry_price": 0.0,
                    "entry_type": "market" | "limit",
                    "tp": [
                        {{"price": 0.0, "percent": 50}}
                    ],
                    "sl": 0.0,
                    "leverage": 1,
                    "amount": 0.0,
                    "network": "solana" | "ethereum" | "bsc" | "unknown"
                }}
            }}
        ]
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
        if not self._pplx_client:
            self._pplx_client = AsyncPerplexity(api_key=api_key)
        
        # El SDK de Perplexity sigue la interfaz de OpenAI
        response = await self._pplx_client.chat.completions.create(
            model="sonar-pro", # Cambiado de reasoning-pro a sonar-pro para evitar bloqueos de seguridad
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "text"} # PPLX requiere explícitamente 'text' en algunos casos para evitar 400
        )
        return response.choices[0].message.content

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

    def _parse_response(self, content: str) -> List[SignalAnalysis]:
        content = content.strip()
        
        # 1. Intentar extraer JSON usando regex (ahora buscando [] o {})
        json_match = re.search(r'([\[\{].*[\]\}])', content, re.DOTALL)
        if json_match:
            content = json_match.group(1)
        
        try:
            data = json.loads(content)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse AI JSON: {e} | Content: {content[:100]}...")
            return [self._default_hold(f"Error parseando JSON de IA: {str(e)}")]

        # Si es un objeto único, convertirlo en lista
        if isinstance(data, dict):
            items = [data]
        elif isinstance(data, list):
            items = data
        else:
            return [self._default_hold("Formato de respuesta de IA inválido (no es lista u objeto)")]

        results = []
        for item in items:
            results.append(self._parse_single_item(item))
        return results

    def _parse_single_item(self, data: dict) -> SignalAnalysis:
        params_data = data.get("parameters", {})
        
        tp_list = [TakeProfit(price=t["price"], percent=t["percent"]) for t in params_data.get("tp", []) if isinstance(t, dict) and "price" in t]
        
        params = TradingParameters(
            entry_price=params_data.get("entry_price"),
            entry_type=params_data.get("entry_type", "market"),
            tp=tp_list,
            sl=params_data.get("sl"),
            leverage=params_data.get("leverage", 1),
            amount=params_data.get("amount"),
            network=params_data.get("network")
        )

        # Mapeo robusto de Decision
        decision_val = data.get("decision", "HOLD").upper()
        if decision_val not in [d.value for d in Decision]:
            decision = Decision.HOLD
        else:
            decision = Decision(decision_val)

        # Mapeo robusto de MarketType
        market_val = data.get("market_type", "SPOT").upper()
        if market_val == "CEX": market_val = "SPOT"
        if market_val not in [m.value for m in MarketType]:
            market_type = MarketType.SPOT
        else:
            market_type = MarketType(market_val)

        return SignalAnalysis(
            decision=decision,
            symbol=data.get("symbol", "UNKNOWN"),
            market_type=market_type,
            confidence=data.get("confidence", 0.0),
            reasoning=data.get("reasoning", "Parsed with safety defaults"),
            is_safe=data.get("is_safe", False),
            risk_score=data.get("risk_score", 10.0),
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
