import logging
from api.src.domain.models.schemas import AnalysisResult, ExecutionResult
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
        """Prueba la conexión delegando a CCXTService"""
        return await self.ccxt_provider.test_connection_private(exchange_id, api_key, secret, password, uid)

    async def fetch_balance(self, user_id: str, exchange_id: Optional[str] = None) -> Dict[str, Any]:
        """Obtiene el balance total del usuario delegando a CCXTService"""
        try:
            config = await get_app_config(user_id)
            exchanges_config = config.get("exchanges", []) if config else []
            
            # Identificar el exchange objetivo
            ex_cfg = None
            if exchange_id:
                ex_cfg = next((e for e in exchanges_config if e["exchangeId"] == exchange_id and e.get("isActive", True)), None)
            else:
                ex_cfg = next((e for e in exchanges_config if e.get("isActive", True)), None)
            
            if not ex_cfg or not ex_cfg.get("apiKey"):
                logger.error(f"CEXService: Credenciales no encontradas para {exchange_id or 'active exchange'}")
                return {}

            return await self.ccxt_provider.fetch_balance_private(
                ex_cfg["exchangeId"], 
                ex_cfg["apiKey"], 
                ex_cfg["secret"], 
                ex_cfg.get("password"), 
                ex_cfg.get("uid")
            )
        except Exception as e:
            logger.error(f"CEXService: Error al obtener balance unificado: {e}")
            return {}

    async def get_exchange_instance(self, user_id: str, exchange_id: Optional[str] = None):
        """Obtiene una instancia (persistent/cached si existe) usando CCXTService"""
        config = await get_app_config(user_id)
        if not config or "exchanges" not in config:
            return None, None

        # 1. Identificar configuración
        ex_cfg = None
        if exchange_id:
            ex_cfg = next((e for e in config["exchanges"] if e["exchangeId"] == exchange_id and e.get("isActive", True)), None)
        else:
            ex_cfg = next((e for e in config["exchanges"] if e.get("isActive", True)), None)
            if ex_cfg: exchange_id = ex_cfg["exchangeId"]
        
        if not ex_cfg or not ex_cfg.get("apiKey"):
            return None, config

        cache_key = f"{user_id}_{exchange_id}"
        if cache_key in self.exchanges:
            return self.exchanges[cache_key], config

        # 2. Crear instancia usando CCXTService
        instance = await self.ccxt_provider.get_private_instance(
            exchange_id, 
            ex_cfg["apiKey"], 
            ex_cfg["secret"], 
            ex_cfg.get("password"), 
            ex_cfg.get("uid")
        )
        if instance:
            self.exchanges[cache_key] = instance
        
        if instance:
            self.exchanges[cache_key] = instance
        
        return instance, config

    async def get_public_exchange_instance(self, exchange_id: str):
        """Obtiene una instancia PÚBLICA (sin claves) para datos de mercado"""
        if not exchange_id: return None
        
        if exchange_id in self.public_exchanges:
            return self.public_exchanges[exchange_id]
            
        instance = await self.ccxt_provider.create_public_instance(exchange_id)
        if instance:
            self.public_exchanges[exchange_id] = instance
            
        return instance

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

            # Lógica real con CCXT
            logger.info(f"Ejecutando {side.upper()} REAL en {exchange.id} para {symbol} con monto {amount}")
            
            # Normalizar tipo de mercado (ccxt usa 'spot', 'swap', 'future', etc.)
            market_type = 'spot' if analysis.market_type == 'SPOT' else 'swap'
            
            try:
                # Asegurar que el mercado esté cargado
                await exchange.load_markets()
                
                # Crear orden de mercado
                params = {}
                if market_type != 'spot' and analysis.parameters:
                    leverage = analysis.parameters.get('leverage', 1)
                    # Configurar apalancamiento si es futures/swap y el exchange lo soporta
                    if hasattr(exchange, 'set_leverage'):
                        try:
                            await exchange.set_leverage(leverage, symbol)
                        except Exception as lev_e:
                            logger.warning(f"No se pudo establecer apalancamiento: {lev_e}")

                order = await exchange.create_order(
                    symbol=symbol,
                    type='market',
                    side=side.lower(),
                    amount=amount,
                    params=params
                )
                
                logger.info(f"Orden real ejecutada con éxito: {order.get('id')}")
                return ExecutionResult(
                    success=True, 
                    order_id=order.get('id'),
                    message=f"Orden real {side.upper()} ejecutada en {exchange.id}",
                    details=order
                )
            except ccxt.InsufficientFunds as e:
                return ExecutionResult(success=False, message=f"Fondos insuficientes: {str(e)}")
            except ccxt.InvalidOrder as e:
                return ExecutionResult(success=False, message=f"Orden inválida: {str(e)}")
            except Exception as e:
                logger.error(f"Error ejecutanzo orden en {exchange.id}: {e}")
                return ExecutionResult(success=False, message=f"Error en exchange: {str(e)}")

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
