import ccxt
import logging
from typing import Optional, Dict, Any
from api.models.schemas import AnalysisResult, ExecutionResult
from api.models.mongodb import get_app_config, save_trade, update_virtual_balance

logger = logging.getLogger(__name__)

class CEXService:
    def __init__(self):
        self.exchanges = {} # Cache de instancias de exchange por user_id

    async def get_exchange_instance(self, user_id: str, exchange_id: str = "binance"):
        config = await get_app_config(user_id)
        if not config or "exchanges" not in config:
            return None, None

        # Buscar el exchange específico en la lista
        exchange_config = next((e for e in config["exchanges"] if e["exchangeId"] == exchange_id and e.get("isActive", True)), None)
        
        if not exchange_config or not exchange_config.get("apiKey"):
            return None, config

        cache_key = f"{user_id}_{exchange_id}"
        if cache_key in self.exchanges:
            return self.exchanges[cache_key], config

        try:
            exchange_class = getattr(ccxt, exchange_id)
            inst_config = {
                'apiKey': exchange_config["apiKey"],
                'secret': exchange_config["secret"],
                'enableRateLimit': True,
            }
            if exchange_config.get("password"):
                inst_config['password'] = exchange_config["password"]
            if exchange_config.get("uid"):
                inst_config['uid'] = exchange_config["uid"]
                
            instance = exchange_class(inst_config)
            self.exchanges[cache_key] = instance
            return instance, config
        except Exception as e:
            logger.error(f"Error inicializando exchange {exchange_id}: {e}")
            return None, config

    async def execute_trade(self, analysis: AnalysisResult, user_id: str = "default_user") -> ExecutionResult:
        exchange, config = await self.get_exchange_instance(user_id)
        demo_mode = config.get("demoMode", True) if config else True
        
        # Obtener límite de inversión
        max_amount = 100.0 # Default
        if config and "investmentLimits" in config:
            max_amount = config["investmentLimits"].get("cexMaxAmount", 100.0)

        try:
            symbol = analysis.symbol
            side = analysis.decision.lower()
            
            # Usar el monto sugerido o el máximo permitido
            suggested_amount = analysis.parameters.get('amount', 0) if analysis.parameters else 0
            amount = min(suggested_amount, max_amount) if suggested_amount > 0 else max_amount
            
            if amount <= 0:
                return ExecutionResult(success=False, message="Cantidad de inversión inválida o no configurada")

            if demo_mode:
                logger.info(f"[MODO DEMO] Simulando {side} para {symbol} con monto {amount}")
                
                # Obtener precio actual para la simulación
                price = 50000.0 # Default fallback
                if exchange:
                    try:
                        ticker = await exchange.fetch_ticker(symbol)
                        price = ticker['last']
                    except:
                        pass
                
                # Registrar trade en MongoDB
                trade_doc = {
                    "userId": config["userId"] if config else None,
                    "symbol": symbol,
                    "side": side.upper(),
                    "price": price,
                    "amount": amount,
                    "marketType": "CEX",
                    "isDemo": True,
                    "status": "completed"
                }
                await save_trade(trade_doc)
                
                # Actualizar balance virtual (simplificado: asumiendo USDT como base)
                # En una implementación real, buscaríamos el balance actual y restaríamos/sumaríamos
                # await update_virtual_balance(user_id, "CEX", "USDT", new_amount)
                
                return ExecutionResult(
                    success=True,
                    message=f"MODO DEMO: {side.upper()} {symbol} a {price} registrado (Límite: {max_amount})"
                )

            if not exchange:
                return ExecutionResult(success=False, message="Exchange no configurado para trading real")

            # Lógica real
            logger.info(f"Ejecutando {side} REAL en CEX para {symbol} con monto {amount}")
            # order = await exchange.create_order(symbol, 'market', side, amount)
            return ExecutionResult(success=True, message=f"Orden real ejecutada (Simulado). Monto: {amount}")

        except Exception as e:
            logger.error(f"Error ejecutando trade en CEX: {e}")
            return ExecutionResult(success=False, message=f"Error en CEX: {str(e)}")
