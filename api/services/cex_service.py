import ccxt
import logging
from typing import Optional, Dict, Any
from api.models.schemas import AnalysisResult, ExecutionResult
from api.models.mongodb import get_app_config, save_trade, update_virtual_balance

logger = logging.getLogger(__name__)

class CEXService:
    def __init__(self):
        self.exchanges = {} # Cache de instancias de exchange por user_id

    async def test_connection(self, exchange_id: str, api_key: str, secret: str, password: str = None, uid: str = None):
        try:
            exchange_class = getattr(ccxt, exchange_id)
            inst_config = {
                'apiKey': api_key,
                'secret': secret,
                'enableRateLimit': True,
            }
            if password:
                inst_config['password'] = password
            if uid:
                inst_config['uid'] = uid
                
            instance = exchange_class(inst_config)
            # Try fetching balance as a connectivity test
            result = instance.fetch_balance()
            # Check if it's a coroutine (async) or direct result (sync)
            import inspect
            if inspect.iscoroutine(result):
                await result
            # Close if method exists
            if hasattr(instance, 'close'):
                close_result = instance.close()
                if inspect.iscoroutine(close_result):
                    await close_result
            return True, "Conexión exitosa"
        except Exception as e:
            logger.error(f"Error testing connection {exchange_id}: {e}")
            return False, str(e)

    async def get_exchange_instance(self, user_id: str, exchange_id: str = "binance"):
        config = await get_app_config(user_id)
        if not config or "exchanges" not in config:
            return None, None

        # 1. Intentar encontrar el exchange solicitado
        exchange_config = next((e for e in config["exchanges"] if e["exchangeId"] == exchange_id and e.get("isActive", True)), None)
        
        # 2. Si no se encuentra (o es el default 'binance' pero el usuario tiene otro), 
        # usar el primer exchange activo de la lista
        if not exchange_config:
            exchange_config = next((e for e in config["exchanges"] if e.get("isActive", True)), None)
            if exchange_config:
                exchange_id = exchange_config["exchangeId"]
        
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

    async def get_current_price(self, symbol: str, user_id: str) -> float:
        """Obtiene el precio actual de un símbolo para un usuario configurado"""
        try:
            exchange, config = await self.get_exchange_instance(user_id)
            
            # Determinar qué exchangeId usar para la consulta pública
            exchange_id = "binance"
            if config and config.get("exchanges"):
                # Usar el primero activo o el primero de la lista
                active_ex = next((e for e in config["exchanges"] if e.get("isActive", True)), config["exchanges"][0])
                exchange_id = active_ex["exchangeId"]

            # Si no hay instancia autenticada, crear una pública temporal
            if not exchange:
                logger.info(f"Usando instancia pública de {exchange_id} para consultar precio de {symbol}")
                exchange = getattr(ccxt, exchange_id)()
                ticker = await exchange.fetch_ticker(symbol)
                await exchange.close()
            else:
                ticker = await exchange.fetch_ticker(symbol)
            
            return ticker['last']
        except Exception as e:
            logger.error(f"Error obteniendo precio para {symbol}: {e}")
            return 0.0

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
                
                # Obtener precio actual para la simulación usando ccxt del exchange configurado
                price = 0.0
                try:
                    # Determinar exchangeId de reserva
                    exchange_id = "binance"
                    if config and config.get("exchanges"):
                        active_ex = next((e for e in config["exchanges"] if e.get("isActive", True)), config["exchanges"][0])
                        exchange_id = active_ex["exchangeId"]

                    # Si no hay instancia de exchange, crear una pública temporal para el precio
                    temp_exchange = exchange if exchange else getattr(ccxt, exchange_id)()
                    ticker = await temp_exchange.fetch_ticker(symbol)
                    price = ticker['last']
                    if not exchange: await temp_exchange.close()
                except Exception as e:
                    logger.error(f"Error obteniendo precio para modo demo: {e}")
                    return ExecutionResult(success=False, message=f"No se pudo obtener el precio para {symbol}")
                
                # Registrar trade en MongoDB con estado 'open' para monitoreo
                trade_doc = {
                    "userId": config["userId"] if config else None,
                    "symbol": symbol,
                    "side": side.upper(),
                    "entryPrice": price,
                    "currentPrice": price,
                    "amount": amount,
                    "marketType": "CEX",
                    "isDemo": True,
                    "status": "open", # Abierto para monitoreo de TP/SL
                    "tp": analysis.parameters.get('tp') if analysis.parameters else None,
                    "sl": analysis.parameters.get('sl') if analysis.parameters else None,
                    "createdAt": datetime.utcnow()
                }
                await save_trade(trade_doc)
                
                # Actualizar balance virtual inmediatamente al abrir la posición
                user = await db.users.find_one({"openId": user_id})
                if user:
                    current_balance_doc = await db.virtual_balances.find_one({
                        "userId": user["_id"],
                        "marketType": "CEX",
                        "asset": "USDT"
                    })
                    
                    current_balance = current_balance_doc["amount"] if current_balance_doc else config.get("virtualBalances", {}).get("cex", 10000)
                    
                    # Al comprar en demo, restamos el monto del balance virtual
                    if side == "buy":
                        new_balance = current_balance - amount
                        await update_virtual_balance(user_id, "CEX", "USDT", new_balance)
                        logger.info(f"Virtual balance updated (Demo Buy): {current_balance} -> {new_balance}")
                
                return ExecutionResult(
                    success=True,
                    message=f"MODO DEMO: Posición {side.upper()} abierta para {symbol} a {price}. Monitoreando TP/SL."
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
