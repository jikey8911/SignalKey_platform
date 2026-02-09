import logging
from api.src.domain.models.schemas import AnalysisResult, ExecutionResult
from api.src.domain.entities.signal import SignalAnalysis, Decision, MarketType, TradingParameters, TakeProfit
from api.src.adapters.driven.persistence.mongodb import get_app_config, save_trade, update_virtual_balance, db
from api.src.adapters.driven.exchange.ccxt_adapter import ccxt_service
import ccxt.async_support as ccxt 
from datetime import datetime
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

class CEXService:
    def __init__(self, ccxt_adapter=None):
        self.exchanges = {} 
        self.public_exchanges = {} 
        if ccxt_adapter:
            self.ccxt_provider = ccxt_adapter
        else:
            from api.src.adapters.driven.exchange.ccxt_adapter import ccxt_service
            self.ccxt_provider = ccxt_service

    async def close_all(self):
        await self.ccxt_provider.close_all()
        logger.info("CEXService: Todas las sesiones cerradas vía CCXTProvider.")

    async def test_connection(self, exchange_id: str, api_key: str, secret: str, password: str = None, uid: str = None):
        try:
            exchange = await self.ccxt_provider._get_exchange(exchange_id)
            if not exchange.markets:
                await exchange.load_markets()
            return True, "Conexión exitosa"
        except Exception as e:
            return False, f"Error de conexión: {str(e)}"

    async def fetch_balance(self, user_id: str, exchange_id: Optional[str] = None) -> Dict[str, Any]:
        try:
            balances = await self.ccxt_provider.fetch_balance(user_id, exchange_id or "binance")
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
        if not exchange_id:
            config = await get_app_config(user_id)
            if config and config.get("exchanges"):
                active_ex = next((e for e in config["exchanges"] if e.get("isActive", True)), None)
                if active_ex:
                    exchange_id = active_ex["exchangeId"]
        
        exchange_id = exchange_id or "binance"
        instance = await self.ccxt_provider._get_exchange(exchange_id, user_id)
        return instance, None 

    async def get_public_exchange_instance(self, exchange_id: str):
        return await self.ccxt_provider._get_exchange(exchange_id)

    async def monitor_price_with_alerts(self, exchange_id: str, symbol: str, targets: List[float], callback: callable):
        """
        Orquestador Hexagonal: Conecta la aplicación con el flujo inteligente en el adaptador.
        """
        symbol = self._normalize_symbol(symbol)
        logger.info(f"📡 Iniciando monitoreo inteligente para {symbol} en {exchange_id} (Targets: {targets})")
        
        async for price in self.ccxt_provider.watch_high_precision_stream(exchange_id, symbol, targets):
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(symbol, price)
                else:
                    callback(symbol, price)
            except Exception as e:
                logger.error(f"Error en callback de monitoreo para {symbol}: {e}")

    def _normalize_symbol(self, symbol: str) -> str:
        if not symbol or not str(symbol).strip(): 
            return "UNKNOWN/USDT"
        symbol = str(symbol).upper().strip().replace("-", "/").replace("_", "/")
        if "/" not in symbol:
            for quote in ["USDT", "USDC", "BUSD", "BTC", "ETH"]:
                if symbol.endswith(quote) and symbol != quote:
                    return f"{symbol[:-len(quote)]}/{quote}"
        return symbol

    async def get_current_price(self, symbol: str, user_id: str, exchange_id: Optional[str] = None) -> float:
        symbol = self._normalize_symbol(symbol)
        
        if exchange_id:
            try:
                price = await self.fetch_ticker_price(symbol, user_id, exchange_id)
                if price > 0: return price
            except Exception:
                pass 

        try:
            config = await get_app_config(user_id)
            active_exchanges = []
            if config and config.get("exchanges"):
                active_exchanges = [e for e in config["exchanges"] if e.get("isActive", True)]

            for ex_cfg in active_exchanges:
                ex_id = ex_cfg["exchangeId"]
                if exchange_id and ex_id == exchange_id: continue 
                try:
                    price = await self.fetch_ticker_price(symbol, user_id, ex_id)
                    if price > 0: return price
                except Exception as e:
                    logger.debug(f"CEXService: {ex_id} no pudo proveer precio para {symbol}: {e}")

            if not active_exchanges and not exchange_id:
                return await self.fetch_ticker_price(symbol, user_id, "binance", is_fallback=True)
            return 0.0
        except Exception as e:
            logger.error(f"CEXService: Error crítico en búsqueda de precio para {symbol}: {e}")
            return 0.0

    async def fetch_ticker_price(self, symbol: str, user_id: str, exchange_id: str, is_fallback: bool = False) -> float:
        try:
            return await self.ccxt_provider.get_public_current_price(symbol, exchange_id)
        except Exception as e:
            if not is_fallback:
                logger.debug(f"CEXService: Error ticker {exchange_id} {symbol}: {e}")
            return 0.0

    async def execute_trade(self, analysis: AnalysisResult, user_id: str = "default_user", exchange_id: str = "binance") -> ExecutionResult:
        exchange_id = exchange_id or "binance"
        exchange, config = await self.get_exchange_instance(user_id, exchange_id)
        demo_mode = config.get("demoMode", True) if config else True
        
        max_amount = 100.0
        if config and "investmentLimits" in config:
            max_amount = config["investmentLimits"].get("cexMaxAmount", 100.0)

        try:
            symbol = analysis.symbol
            side = analysis.decision.lower()
            suggested_amount = analysis.parameters.get('amount', 0) if analysis.parameters else 0
            amount = min(suggested_amount, max_amount) if suggested_amount > 0 else max_amount
            
            if amount <= 0:
                return ExecutionResult(success=False, message="Cantidad de inversión inválida")

            if demo_mode:
                price = await self.get_current_price(symbol, user_id, exchange_id)
                if price <= 0:
                    return ExecutionResult(success=False, message=f"No se pudo obtener el precio para {symbol} en {exchange_id}")
                
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
                    "marketType": analysis.market_type,
                    "isDemo": True,
                    "status": status,
                    "tp": analysis.parameters.get('tp') if analysis.parameters else [],
                    "sl": analysis.parameters.get('sl') if analysis.parameters else None,
                    "leverage": analysis.parameters.get('leverage', 1),
                    "exchangeId": exchange_id, 
                    "createdAt": datetime.utcnow()
                }
                await save_trade(trade_doc)
                
                user = await db.users.find_one({"openId": user_id})
                if user:
                    if side == "buy":
                        await update_virtual_balance(user_id, "CEX", "USDT", -amount, is_relative=True)
                    elif side == "sell":
                        await update_virtual_balance(user_id, "CEX", "USDT", amount, is_relative=True)
                
                return ExecutionResult(
                    success=True,
                    message=f"MODO DEMO: Posición {side.upper()} en {exchange_id} para {symbol}."
                )

            if not exchange:
                return ExecutionResult(success=False, message="Exchange no inicializado")

            logger.info(f"Delegando ejecución real a CCXTService para {symbol} en {exchange_id}")
            trade_result_dict = await self.ccxt_provider.execute_trade(
                symbol=symbol,
                side=side,
                amount=amount,
                price=analysis.parameters.get('entry_price') if analysis.parameters else None,
                user_id=user_id,
                exchange_id=exchange_id
            )
            
            if trade_result_dict.get("success"):
                order = trade_result_dict.get("details", {})
                avg_price = order.get('average') or order.get('price') or 0
                return ExecutionResult(
                    success=True,
                    order_id=trade_result_dict.get("order_id"),
                    message=f"Orden real {side.upper()} ejecutada en {exchange_id}",
                    details={"price": avg_price, "amount": order.get('amount', amount)}
                )
            else:
                return ExecutionResult(success=False, message=f"Fallo en ejecución: {trade_result_dict.get('message')}")

        except Exception as e:
            logger.error(f"Error ejecutando trade en CEX: {e}")
            return ExecutionResult(success=False, message=f"Error en CEXService: {str(e)}")

    async def fetch_open_orders(self, user_id: str, symbol: Optional[str] = None, exchange_id: Optional[str] = None) -> List[Dict[str, Any]]:
        try:
            return await self.ccxt_provider.fetch_open_orders(symbol, user_id=user_id, exchange_id=exchange_id or 'binance')
        except Exception as e:
            logger.error(f"Error fetching open orders: {e}")
            return []

    async def fetch_positions(self, user_id: str, symbols: Optional[List[str]] = None, exchange_id: Optional[str] = None) -> List[Dict[str, Any]]:
        return []

    async def get_historical_data(self, symbol: str, timeframe: str, limit: int = 1500, use_random_date: bool = False, user_id: str = "default_user", exchange_id: str = "binance") -> Any:
        import pandas as pd
        try:
            return await self.ccxt_provider.get_historical_data(
                symbol=symbol,
                timeframe=timeframe,
                limit=limit,
                use_random_date=use_random_date,
                user_id=user_id,
                exchange_id=exchange_id 
            )
        except Exception as e:
            logger.error(f"Error CEXService.get_historical_data for {symbol} on {exchange_id}: {e}")
            return pd.DataFrame()

    async def get_historical_candles(self, exchange_id: str, symbol: str, timeframe: str, limit: int = 100) -> List[Dict[str, Any]]:
        try:
            df = await self.ccxt_provider.get_historical_data(
                symbol=symbol, timeframe=timeframe, limit=limit, exchange_id=exchange_id
            )
            if df.empty: return []
            return df.reset_index().to_dict('records')
        except Exception as e:
            logger.error(f"Error fetching historical candles for {symbol}: {e}")
            return []