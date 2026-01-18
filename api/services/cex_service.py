import ccxt.async_support as ccxt
import logging
from typing import Optional, Dict, Any
from api.models.schemas import AnalysisResult, ExecutionResult
from api.models.mongodb import get_app_config, save_trade, update_virtual_balance

logger = logging.getLogger(__name__)

class CEXService:
    def __init__(self):
        self.exchanges = {} # Cache de instancias de exchange por user_id
        self.public_exchanges = {} # Cache de instancias públicas por exchange_id

    async def close_all(self):
        """Cierra todas las sesiones de exchange abiertas"""
        for exchange in self.exchanges.values():
            try:
                await exchange.close()
            except:
                pass
        for exchange in self.public_exchanges.values():
            try:
                await exchange.close()
            except:
                pass
        self.exchanges = {}
        self.public_exchanges = {}
        logger.info("CEXService: Todas las sesiones cerradas.")

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

    def _normalize_symbol(self, symbol: str) -> str:
        """Normaliza el símbolo al formato de ccxt (e.g. BTC/USDT)"""
        if not symbol or not str(symbol).strip(): 
            return "UNKNOWN/USDT"
        
        symbol = str(symbol).upper().strip().replace("-", "/").replace("_", "/")
        
        if "/" not in symbol:
            # Intento básico de separar si termina en USDT, USDC, BTC, etc.
            for quote in ["USDT", "USDC", "BUSD", "BTC", "ETH"]:
                if symbol.endswith(quote) and symbol != quote:
                    return f"{symbol[:-len(quote)]}/{quote}"
        return symbol

    async def get_current_price(self, symbol: str, user_id: str) -> float:
        """Obtiene el precio actual buscando en todos los exchanges activos del usuario"""
        symbol = self._normalize_symbol(symbol)
        if "UNKNOWN" in symbol:
            return 0.0

        try:
            config = await get_app_config(user_id)
            active_exchanges = []
            
            if config and config.get("exchanges"):
                active_exchanges = [e for e in config["exchanges"] if e.get("isActive", True)]

            # 1. Intentar buscar en cada exchange configurado por el usuario
            for ex_cfg in active_exchanges:
                ex_id = ex_cfg["exchangeId"]
                try:
                    price = await self._get_price_from_exchange(symbol, user_id, ex_id)
                    if price > 0:
                        return price
                except Exception as e:
                    logger.debug(f"CEXService: {ex_id} no pudo proveer precio para {symbol}: {e}")

            # 2. Fallback: Si no se encontró en sus exchanges, buscar en binance por defecto (como referencia global)
            return await self._get_price_from_exchange(symbol, user_id, "binance", is_fallback=True)

        except Exception as e:
            logger.error(f"CEXService: Error crítico en cadena de búsqueda de precio para {symbol}: {e}")
            return 0.0

    async def _get_price_from_exchange(self, symbol: str, user_id: str, exchange_id: str, is_fallback: bool = False) -> float:
        """Helper para obtener precio de un exchange específico (con o sin auth)"""
        try:
            # Intentar obtener instancia (autenticada o pública)
            exchange, _ = await self.get_exchange_instance(user_id, exchange_id)
            
            if not exchange:
                # Si no hay instancia auth, usar/crear pública
                if exchange_id not in self.public_exchanges:
                    exchange_class = getattr(ccxt, exchange_id)
                    self.public_exchanges[exchange_id] = exchange_class({
                        'enableRateLimit': True,
                        'options': {'defaultType': 'spot'}
                    })
                exchange = self.public_exchanges[exchange_id]

            # Cargar mercados y validar
            if not exchange.markets:
                await exchange.load_markets()
            
            if symbol in exchange.symbols:
                ticker = await exchange.fetch_ticker(symbol)
                return float(ticker['last'])
            
            return 0.0
        except Exception as e:
            if not is_fallback:
                logger.debug(f"CEXService: Error consultando {exchange_id} para {symbol}: {e}")
            return 0.0

    # Eliminado _get_price_from_binance ya que está integrado en la lógica dinámica de búsqueda

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
                
                # Obtener precio actual para la simulación usando el sistema centralizado de precios
                price = await self.get_current_price(symbol, user_id)
                if price <= 0:
                    return ExecutionResult(success=False, message=f"No se pudo obtener el precio para {symbol}")
                
                # Registrar trade en MongoDB con estado 'pending' para monitoreo de entrada
                # Si el precio actual ya es igual o mejor que el entry_price, se pone en 'open'
                entry_price = analysis.parameters.get('entry_price') or price
                status = "open" if price <= entry_price and side == "buy" else "pending"
                if side == "sell" and price >= entry_price: status = "open"

                trade_doc = {
                    "userId": config["userId"] if config else None,
                    "symbol": symbol,
                    "side": side.upper(),
                    "entryPrice": entry_price,
                    "currentPrice": price,
                    "amount": amount,
                    "marketType": analysis.market_type, # SPOT o FUTURES
                    "isDemo": True,
                    "status": status,
                    "tp": analysis.parameters.get('tp') if analysis.parameters else [],
                    "sl": analysis.parameters.get('sl') if analysis.parameters else None,
                    "leverage": analysis.parameters.get('leverage', 1),
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
                        await update_virtual_balance(user_id, "CEX", "USDT", -amount, is_relative=True)
                        logger.info(f"Virtual balance updated (Demo Buy): -{amount}")
                    elif side == "sell":
                        await update_virtual_balance(user_id, "CEX", "USDT", amount, is_relative=True)
                        logger.info(f"Virtual balance updated (Demo Sell): +{amount}")
                
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
