import logging
from api.src.domain.models.schemas import AnalysisResult, ExecutionResult
from api.src.domain.entities.signal import SignalAnalysis, Decision, MarketType, TradingParameters, TakeProfit
from api.src.adapters.driven.persistence.mongodb import get_app_config, save_trade, update_virtual_balance, db
from api.src.adapters.driven.exchange.ccxt_adapter import ccxt_service
import ccxt.async_support as ccxt # Para excepciones
from datetime import datetime
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

class CEXService:
    def __init__(self, ccxt_adapter=None):
        self.exchanges = {} # Cache de instancias de exchange por user_id
        self.public_exchanges = {} # Cache de instancias públicas por exchange_id
        # Dependency Injection or Fallback to global
        if ccxt_adapter:
            self.ccxt_provider = ccxt_adapter
        else:
            from api.src.adapters.driven.exchange.ccxt_adapter import ccxt_service
            self.ccxt_provider = ccxt_service

    async def close_all(self):
        """Cierra todas las sesiones de exchange gestionadas por el proveedor central"""
        await self.ccxt_provider.close_all()
        logger.info("CEXService: Todas las sesiones cerradas vía CCXTProvider.")

    async def test_connection(self, exchange_id: str, api_key: str, secret: str, password: str = None, uid: str = None):
        """Prueba la conexión delegando a CCXTService"""
        success = await self.ccxt_provider.test_connection(exchange_id, api_key, secret, password, uid)
        return success, "Conexión exitosa" if success else "Error de conexión (Verifica tus APIs)"

    async def fetch_balance(self, user_id: str, exchange_id: Optional[str] = None) -> Dict[str, Any]:
        """Obtiene el balance total del usuario delegando a CCXTService"""
        try:
            balances = await self.ccxt_provider.fetch_balance(user_id, exchange_id or "binance")
            # Convertir lista de objetos Balance a dict para compatibilidad con el resto de la app si es necesario
            res = {"total": {}, "free": {}, "used": {}}
            for b in balances:
                res["total"][b.asset] = b.total
                res["free"][b.asset] = b.free
                res["used"][b.asset] = b.used
            return res
        except Exception as e:
            logger.error(f"CEXService: Error al obtener balance: {e}")
            return {}

    async def get_exchange_instance(self, user_id: str, exchange_id: Optional[str] = None):
        """Obtiene una instancia (persistent/cached si existe) usando CCXTService Pro"""
        # Obtenemos config del usuario para determinar exchangeId si no se provee
        if not exchange_id:
            config = await get_app_config(user_id)
            if config and config.get("exchanges"):
                active_ex = next((e for e in config["exchanges"] if e.get("isActive", True)), None)
                if active_ex:
                    exchange_id = active_ex["exchangeId"]
        
        exchange_id = exchange_id or "binance"
        
        # Delegamos a CCXTService que ya maneja su propio cache (user_instances)
        instance = await self.ccxt_provider._get_exchange(exchange_id, user_id)
        return instance, None # Retornamos None para config si no es estrictamente necesario aquí

    async def get_public_exchange_instance(self, exchange_id: str):
        """Obtiene una instancia PÚBLICA (sin claves) delegando al cache de CCXTService"""
        return await self.ccxt_provider._get_exchange(exchange_id)

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
                    price = await self.fetch_ticker_price(symbol, user_id, ex_id)
                    if price > 0:
                        return price
                except Exception as e:
                    logger.debug(f"CEXService: {ex_id} no pudo proveer precio para {symbol}: {e}")

            # 2. Si no hay exchanges configurados, no podemos obtener precio reliable
            if not active_exchanges:
                logger.warning(f"CEXService: No hay exchanges activos para obtener precio de {symbol}")
                return 0.0
            
            return 0.0

        except Exception as e:
            logger.error(f"CEXService: Error crítico en cadena de búsqueda de precio para {symbol}: {e}")
            return 0.0

    async def fetch_ticker_price(self, symbol: str, user_id: str, exchange_id: str, is_fallback: bool = False) -> float:
        """Helper para obtener el último precio delegando a CCXTService para la instancia pública"""
        try:
            exchange, _ = await self.get_exchange_instance(user_id, exchange_id)
            
            if not exchange:
                # Usar CCXTService para instancia pública cacheada
                exchange = await self.ccxt_provider.create_public_instance(exchange_id)

            if not exchange:
                return 0.0

            if not exchange.markets:
                await exchange.load_markets()
            
            if symbol in exchange.symbols:
                ticker = await exchange.fetch_ticker(symbol)
                return float(ticker['last'])
            
            # Intentar buscar sin la barra si es necesario (algunos exchanges tienen formatos raros)
            alt_symbol = symbol.replace("/", "")
            if alt_symbol in exchange.symbols:
                ticker = await exchange.fetch_ticker(alt_symbol)
                return float(ticker['last'])
                
            return 0.0
        except Exception as e:
            if not is_fallback:
                logger.debug(f"CEXService: Error consultando ticker en {exchange_id} para {symbol}: {e}")
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

            # DELEGACIÓN AL PUERTO (CCXT Service corregido)
            try:
                # El nuevo CCXTService.execute_trade recibe parámetros individuales
                logger.info(f"Delegando ejecución real a CCXTService para {symbol}")
                trade_result_dict = await self.ccxt_provider.execute_trade(
                    symbol=symbol,
                    side=side,
                    amount=amount,
                    price=analysis.parameters.get('entry_price') if analysis.parameters else None,
                    user_id=user_id,
                    exchange_id=config.get("exchange_id", "binance") if config else "binance"
                )
                
                if trade_result_dict.get("success"):
                    order = trade_result_dict.get("details", {})
                    # Extraer precio promedio si es posible
                    avg_price = order.get('average') or order.get('price') or price
                    
                    return ExecutionResult(
                        success=True,
                        order_id=trade_result_dict.get("order_id"),
                        message=f"Orden real {side.upper()} ejecutada exitosamente",
                        details={
                            "price": avg_price,
                            "amount": order.get('amount', amount),
                            "timestamp": datetime.utcnow()
                        }
                    )
                else:
                    return ExecutionResult(success=False, message=f"Fallo en ejecución: {trade_result_dict.get('message')}")

            except Exception as e:
                logger.error(f"Error delegando trade a CCXTAdapter: {e}")
                return ExecutionResult(success=False, message=f"Error interno en delegación: {str(e)}")

        except Exception as e:
            logger.error(f"Error ejecutando trade en CEX: {e}")
            return ExecutionResult(success=False, message=f"Error en CEXService: {str(e)}")

    async def fetch_open_orders(self, user_id: str, symbol: Optional[str] = None, exchange_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Obtiene las órdenes abiertas del usuario"""
        try:
            exchange, _ = await self.get_exchange_instance(user_id, exchange_id)
            if not exchange: return []
            return await exchange.fetch_open_orders(symbol)
        except Exception as e:
            logger.error(f"Error fetching open orders from {exchange_id or 'active exchange'}: {e}")
            return []

    async def fetch_positions(self, user_id: str, symbols: Optional[List[str]] = None, exchange_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Obtiene las posiciones abiertas (para Futures/Swap)"""
        try:
            exchange, _ = await self.get_exchange_instance(user_id, exchange_id)
            if not exchange: return []
            
            if hasattr(exchange, 'fetch_positions'):
                return await exchange.fetch_positions(symbols)
            return []
        except Exception as e:
            logger.error(f"Error fetching positions from {exchange_id or 'active exchange'}: {e}")
            return []

    async def get_historical_data(self, symbol: str, timeframe: str, limit: int = 1500, use_random_date: bool = False, user_id: str = "default_user") -> Any:
        """
        Obtiene datos históricos y los retorna como DataFrame para uso de MLService.
        Adaptador que conecta la capa de Aplicación con Infraestructura (CCXT).
        Ahora soporta user_id para cargar configuración específica del usuario o fallback a sistema.
        """
        import pandas as pd
        try:
            # Usar directamente el método optimizado del provider que ya devuelve DataFrame
            return await self.ccxt_provider.get_historical_data(
                symbol=symbol,
                timeframe=timeframe,
                limit=limit,
                use_random_date=use_random_date,
                user_id=user_id
            )
        except Exception as e:
            logger.error(f"Error CEXService.get_historical_data for {symbol}: {e}")
            return pd.DataFrame()

    async def get_historical_candles(self, exchange_id: str, symbol: str, timeframe: str, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Método wrapper específico para obtener velas en formato lista de diccionarios (no DataFrame),
        compatible con BufferService.
        """
        try:
            # Obtener instancia pública si es solo para datos
            exchange = await self.get_public_exchange_instance(exchange_id)
            if not exchange:
                # Fallback al provider default
                exchange = await self.ccxt_provider.create_public_instance(exchange_id or "binance")

            if not exchange:
                logger.error(f"Cannot get candles: Exchange {exchange_id} not initialized")
                return []

            # Asegurar carga de mercados
            if not exchange.markets:
                try:
                    await exchange.load_markets()
                except Exception as me:
                    logger.warning(f"Error loading markets in get_historical_candles: {me}")

            # Obtener velas
            ohlcv = await exchange.fetch_ohlcv(symbol, timeframe, limit=limit)

            # Formatear
            candles = []
            for candle in ohlcv:
                candles.append({
                    "timestamp": candle[0],
                    "open": candle[1],
                    "high": candle[2],
                    "low": candle[3],
                    "close": candle[4],
                    "volume": candle[5]
                })
            return candles

        except Exception as e:
            logger.error(f"Error fetching historical candles for {symbol}: {e}")
            return []
