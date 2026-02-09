import asyncio
import logging
from typing import Dict, Any, Callable, Set
from api.src.adapters.driven.exchange.ccxt_adapter import ccxt_service

logger = logging.getLogger("MarketStreamService")

class MarketStreamService:
    """
    Orquestador de flujos de datos. 
    Evita duplicar suscripciones al mismo par en el mismo exchange.
    """
    def __init__(self):
        self.listeners: Set[Callable] = set()
        self.active_tasks: Dict[str, asyncio.Task] = {}
        self.latest_data: Dict[str, Any] = {} # "ticker:exchange:symbol" -> ticker_data

    def add_listener(self, callback: Callable):
        self.listeners.add(callback)

    async def subscribe_ticker(self, exchange_id: str, symbol: str) -> Dict[str, Any]:
        task_key = f"ticker:{exchange_id}:{symbol}"
        if task_key not in self.active_tasks:
            self.active_tasks[task_key] = asyncio.create_task(
                self._ticker_loop(exchange_id, symbol)
            )
            logger.info(f"📡 Suscripción Ticker activada: {task_key}")
        
        return self.latest_data.get(task_key, {"last": 0.0})

    async def subscribe_candles(self, exchange_id: str, symbol: str, timeframe: str):
        task_key = f"ohlcv:{exchange_id}:{symbol}:{timeframe}"
        if task_key in self.active_tasks:
            return

        self.active_tasks[task_key] = asyncio.create_task(
            self._ohlcv_loop(exchange_id, symbol, timeframe)
        )
        logger.info(f"🕯️ Suscripción Velas activada: {task_key}")

    async def subscribe_trades(self, exchange_id: str, symbol: str):
        task_key = f"trades:{exchange_id}:{symbol}"
        if task_key in self.active_tasks:
            return
        
        self.active_tasks[task_key] = asyncio.create_task(
            self._trades_loop(exchange_id, symbol)
        )
        logger.info(f"⚡ Suscripción Trades (Alta Frecuencia) activada: {task_key}")

    async def unsubscribe(self, task_key: str):
        if task_key in self.active_tasks:
            task = self.active_tasks.pop(task_key)
            task.cancel()
            logger.info(f"🛑 Suscripción desactivada: {task_key}")

    async def _ticker_loop(self, exchange_id: str, symbol: str):
        task_key = f"ticker:{exchange_id}:{symbol}"
        async for ticker in ccxt_service.watch_ticker(exchange_id, symbol):
            self.latest_data[task_key] = ticker
            await self._notify("ticker_update", {
                "exchange": exchange_id,
                "symbol": symbol,
                "ticker": ticker
            })

    async def _ohlcv_loop(self, exchange_id: str, symbol: str, timeframe: str):
        async for ohlcv_list in ccxt_service.watch_ohlcv(exchange_id, symbol, timeframe):
            if not ohlcv_list: continue
            
            # Solo nos interesa la última vela (la que está cambiando o acaba de cerrar)
            last_ohlcv = ohlcv_list[-1]
            candle_data = {
                "timestamp": last_ohlcv[0],
                "open": last_ohlcv[1],
                "high": last_ohlcv[2],
                "low": last_ohlcv[3],
                "close": last_ohlcv[4],
                "volume": last_ohlcv[5]
            }
            
            await self._notify("candle_update", {
                "exchange": exchange_id,
                "symbol": symbol,
                "timeframe": timeframe,
                "candle": candle_data
            })

    async def _trades_loop(self, exchange_id: str, symbol: str):
        task_key_pref = f"ticker:{exchange_id}:{symbol}" # Reusamos la misma key de precio para que sea transparente
        async for trades in ccxt_service.watch_trades(exchange_id, symbol):
            if not trades: continue
            
            # Actualizar el último precio conocido con el último trade para máxima resolución
            last_trade_price = float(trades[-1]['price'])
            if task_key_pref not in self.latest_data:
                self.latest_data[task_key_pref] = {}
            self.latest_data[task_key_pref]['last'] = last_trade_price

            # Notificamos la lista de trades
            await self._notify("trades_update", {
                "exchange": exchange_id,
                "symbol": symbol,
                "trades": trades
            })

    async def _notify(self, event_type: str, data: Dict[str, Any]):
        for listener in self.listeners:
            try:
                if asyncio.iscoroutinefunction(listener):
                    await listener(event_type, data)
                else:
                    listener(event_type, data)
            except Exception as e:
                logger.error(f"Error notificando listener: {e}")

    async def stop(self):
        for task in self.active_tasks.values():
            task.cancel()
        await ccxt_service.close_all()

