import httpx
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List
from api.src.domain.models.schemas import AnalysisResult, ExecutionResult
from api.src.adapters.driven.persistence.mongodb import db, get_app_config, save_trade, update_virtual_balance
from api.config import Config

logger = logging.getLogger(__name__)

class DEXService:
    def __init__(self):
        self.api_key = Config.ZERO_EX_API_KEY
        self.client = httpx.AsyncClient(timeout=30.0)
        
        # Mapeo de redes a dominios de 0x
        self.network_map = {
            "ethereum": "https://api.0x.org",
            "bsc": "https://bsc.api.0x.org",
            "polygon": "https://polygon.api.0x.org",
            "optimism": "https://optimism.api.0x.org",
            "arbitrum": "https://arbitrum.api.0x.org",
            "base": "https://base.api.0x.org",
            "avalanche": "https://avalanche.api.0x.org",
            "fantom": "https://fantom.api.0x.org",
            "celo": "https://celo.api.0x.org"
        }

    async def close_all(self):
        """Cierra el cliente HTTP"""
        await self.client.aclose()
        logger.info("DEXService: Cliente HTTP cerrado.")

    def _get_base_url(self, network: str) -> str:
        return self.network_map.get(network.lower(), "https://api.0x.org")

    async def get_current_price(self, symbol_or_address: str, network: str = "ethereum", user_id: str = "default_user") -> float:
        """
        Obtiene el precio de un token usando 0x Swap API (/swap/v1/price).
        Se asume que buyToken es el token destino y sellToken es la stablecoin de referencia (USDT/USDC/DAI).
        """
        config = await get_app_config(user_id)
        api_key = config.get("zeroExApiKey") or self.api_key
        
        if not api_key:
            logger.warning("ZERO_EX_API_KEY no configurada. Usando placeholder.")
            return 0.0

        base_url = self._get_base_url(network)
        # Por defecto comparamos contra USDT o USDC según la red
        sell_token = "USDC" if network.lower() in ["polygon", "arbitrum", "base", "optimism"] else "USDT"
        
        url = f"{base_url}/swap/v1/price"
        params = {
            "sellToken": sell_token,
            "buyToken": symbol_or_address,
            "sellAmount": "1000000"  # 1 unidad del token base (ajustar decimales si es necesario)
        }
        headers = {"0x-api-key": api_key}

        try:
            response = await self.client.get(url, params=params, headers=headers)
            if response.status_code == 200:
                data = response.json()
                # 0x devuelve 'price' como el número de buyTokens por sellToken
                # Nosotros queremos el precio de 1 buyToken en términos de sellToken
                # precio_usd = 1 / float(data['price'])
                return 1.0 / float(data['price'])
            else:
                logger.error(f"Error en 0x API ({response.status_code}): {response.text}")
                return 0.0
        except Exception as e:
            logger.error(f"Error conectando con 0x API: {e}")
            return 0.0

    async def execute_trade(self, analysis: AnalysisResult, user_id: str = "default_user") -> ExecutionResult:
        config = await get_app_config(user_id)
        demo_mode = config.get("demoMode", True) if config else True
        
        network = analysis.parameters.get('network', 'ethereum') if analysis.parameters else 'ethereum'
        symbol = analysis.symbol
        side = analysis.decision.upper()
        
        # Obtener límites
        max_amount = 50.0 # Default USD
        if config and "investmentLimits" in config:
            max_amount = config["investmentLimits"].get("dexMaxAmount", 50.0)

        suggested_amount = getattr(analysis.parameters, 'amount', 0) if analysis.parameters else 0
        amount = min(suggested_amount, max_amount) if suggested_amount > 0 else max_amount

        # Para 0x, necesitamos direcciones de contrato
        # Si 'symbol' no es una dirección, este servicio podría fallar o necesitar un mapper
        if not symbol.startswith("0x"):
            # TODO: Implementar búsqueda de dirección por símbolo si es necesario
            logger.warning(f"Símbolo {symbol} no parece una dirección de contrato válida para EVM.")

        if demo_mode:
            price = await self.get_current_price(symbol, network, user_id)
            if price <= 0:
                price = getattr(analysis.parameters, 'entry_price', 100.0) or 100.0

            logger.info(f"[0x DEMO] Simulando {side} para {symbol} en {network} a ${price}")
            
            trade_doc = {
                "userId": config["_id"] if config else None,
                "symbol": symbol,
                "side": side,
                "entryPrice": price,
                "currentPrice": price,
                "amount": amount,
                "marketType": "DEX",
                "network": network,
                "provider": "0x",
                "isDemo": True,
                "status": "open",
                "tp": analysis.parameters.tp if analysis.parameters else [],
                "sl": analysis.parameters.sl if analysis.parameters else None,
                "createdAt": datetime.utcnow()
            }
            inserted_id = await save_trade(trade_doc)
            
            # Actualizar balance virtual (usamos USDT/USDC como base para EVM DEX Demo)
            asset = "USDT" 
            if side == "BUY":
                await update_virtual_balance(user_id, "DEX", asset, -amount, is_relative=True)
            elif side == "SELL":
                # En sell, el amount es en USD equivalent
                await update_virtual_balance(user_id, "DEX", asset, amount, is_relative=True)
            
            return ExecutionResult(
                success=True,
                message=f"0x DEMO: {side} {symbol} en {network} abierto a ${price}.",
                details={"tradeId": str(inserted_id)}
            )

        # Lógica real con 0x Swap API
        try:
            api_key = config.get("zeroExApiKey") or self.api_key
            if not api_key:
                return ExecutionResult(success=False, message="ZERO_EX_API_KEY no configurada para trade real.")

            base_url = self._get_base_url(network)
            url = f"{base_url}/swap/v1/quote"
            
            # Ajustar tokens según operación
            sell_token = "USDC" if side == "BUY" else symbol
            buy_token = symbol if side == "BUY" else "USDC"
            
            # TODO: Convertir amount a wei según los decimales del token
            # Por ahora simulamos la construcción del quote
            params = {
                "sellToken": sell_token,
                "buyToken": buy_token,
                "sellAmount": str(int(amount * 10**6)), # Ejemplo para USDC
                "takerAddress": config.get("dexConfig", {}).get("walletAddress")
            }
            
            logger.info(f"Solicitando Quote Real a 0x ({network}): {params}")
            # response = await self.client.get(url, params=params, headers={"0x-api-key": api_key})
            
            return ExecutionResult(
                success=True, 
                message=f"Operación 0x real en {network} para {symbol} enviada (Mock: Quote pendiented de firma)."
            )

        except Exception as e:
            logger.error(f"Error en trade real 0x: {e}")
            return ExecutionResult(success=False, message=str(e))
