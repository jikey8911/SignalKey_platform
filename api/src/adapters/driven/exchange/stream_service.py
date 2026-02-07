import asyncio
import logging
from typing import Dict, Any, Callable, List, Optional
import ccxt.pro as ccxt
from api.src.adapters.driven.exchange.ccxt_adapter import ccxt_service

logger = logging.getLogger(__name__)

class MarketStreamService:
    _instance = None
    
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(MarketStreamService, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
            
        self.exchanges: Dict[str, ccxt.Exchange] = {}
        self.listeners: List[Callable] = []
        self.subscriptions: Dict[str, List[str]] = {} # exchange_id -> list of symbols
        self.running = False
        self._initialized = True
        self.tasks: List[asyncio.Task] = []
        self.loop = None

    def _get_loop(self):
        if self.loop is None:
            try:
                self.loop = asyncio.get_running_loop()
            except RuntimeError:
                logger.warning("No running loop found in MarketStreamService, creating one is not recommended in prod.")
                self.loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self.loop)
        return self.loop

    async def initialize_exchange(self, exchange_id: str, config: Dict[str, Any] = None):
        """Initialize a ccxt.pro exchange instance if not exists."""
        if exchange_id in self.exchanges:
            return

        try:
            # Using ccxt.pro dynamically
            exchange_class = getattr(ccxt, exchange_id)
            if config:
                exchange = exchange_class(config)
            else:
                exchange = exchange_class({
                    'enableRateLimit': True,  # Recommended
                    'options': {'defaultType': 'spot'} # Default, can be overridden
                })

            # Optimization: Try to use Adapter's cached public markets if available to avoid REST call
            try:
                # Attempt to get markets from the REST adapter first
                rest_instance = await ccxt_service.get_public_exchange_instance(exchange_id)
                if rest_instance and rest_instance.markets:
                    exchange.set_markets(rest_instance.markets)
                    logger.info(f"Markets injected from Adapter for {exchange_id}")
                else:
                    # Fallback to direct load
                    await exchange.load_markets()
                    logger.info(f"Markets loaded directly for {exchange_id}")
            except Exception as e:
                logger.warning(f"Failed to load markets for {exchange_id}: {e}")

            self.exchanges[exchange_id] = exchange
            logger.info(f"Initialized WebSocket exchange: {exchange_id}")
            
        except AttributeError:
             logger.error(f"Exchange {exchange_id} not found in ccxt.pro")
        except Exception as e:
             logger.error(f"Failed to init WS exchange {exchange_id}: {e}")

    async def start(self):
        """Start the service."""
        if self.running:
            return
            
        self.running = True
        logger.info("MarketStreamService started")

    async def stop(self):
        """Stop all connections and tasks."""
        self.running = False
        for ex_id, exchange in self.exchanges.items():
            await exchange.close()
            
        for task in self.tasks:
            task.cancel()
        
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)
            
        self.tasks = []
        self.exchanges = {}
        logger.info("MarketStreamService stopped")

    def add_listener(self, callback: Callable):
        """Register a callback for market events."""
        if callback not in self.listeners:
            self.listeners.append(callback)

    async def notify_listeners(self, event_type: str, data: Any):
        """Emit data to all listeners."""
        for listener in self.listeners:
            try:
                if asyncio.iscoroutinefunction(listener):
                    await listener(event_type, data)
                else:
                    listener(event_type, data)
            except Exception as e:
                logger.error(f"Error notifying listener: {e}")

    async def subscribe_ticker(self, exchange_id: str, symbol: str):
        """Subscribe to ticker updates for a symbol."""
        if exchange_id not in self.exchanges:
            await self.initialize_exchange(exchange_id)
            
        exchange = self.exchanges.get(exchange_id)
        if not exchange:
            logger.error(f"Cannot subscribe: {exchange_id} not initialized")
            return
        
        # Check if already subscribed via task checking
        task_name = f"ticker_{exchange_id}_{symbol}"
        active_tasks = [t for t in self.tasks if not t.done()]
        if any(t.get_name() == task_name for t in active_tasks):
            return

        # Create new task
        task = asyncio.create_task(self._watch_ticker_loop(exchange, symbol))
        task.set_name(task_name)
        self.tasks.append(task)
        logger.info(f"Subscribed to ticker {symbol} on {exchange_id}")

    async def _watch_ticker_loop(self, exchange, symbol: str):
        """Internal loop to watch ticker."""
        backoff = 1
        while self.running:
            try:
                # Ensure markets are loaded (using Adapter if possible logic handled in init, but refresh here if needed)
                if not exchange.markets:
                     await exchange.load_markets()

                # This await blocks until update is received
                ticker = await exchange.watch_ticker(symbol)
                
                backoff = 1 # Reset backoff on success

                # Emit event
                await self.notify_listeners("ticker_update", {
                    "exchange": exchange.id,
                    "symbol": symbol,
                    "ticker": ticker
                })
            except Exception as e:
                logger.error(f"Error watching {symbol} on {exchange.id}: {e}")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60) # Exponential backoff

    async def subscribe_candles(self, exchange_id: str, symbol: str, timeframe: str):
        """
        Se suscribe al stream de velas (OHLCV).
        """
        # Clave única para evitar duplicados: binance_BTC/USDT_15m
        stream_key = f"{exchange_id}_{symbol}_{timeframe}"
        
        if stream_key in self.tasks: # Use key check or better task naming check
             # Check if task with this name exists
            active_tasks = [t for t in self.tasks if not t.done()]
            if any(t.get_name() == stream_key for t in active_tasks):
                return

        logger.info(f"🕯️ Suscribiendo a velas {timeframe} para {symbol}")
        
        async def candle_loop():
            try:
                # Determinar el exchange instance (asumiendo gestión dinámica)
                if exchange_id not in self.exchanges:
                    await self.initialize_exchange(exchange_id)
                    
                exchange = self.exchanges.get(exchange_id) 
                if not exchange: return

                backoff = 1
                while self.running:
                    # CCXT watch_ohlcv devuelve una lista de velas. Tomamos la última.
                    try:
                        # Explicit check inside loop to handle reconnections/reloads
                        if not exchange.markets:
                             # Try to reload via adapter first to avoid spam
                             try:
                                 rest_instance = await ccxt_service.get_public_exchange_instance(exchange_id)
                                 if rest_instance and rest_instance.markets:
                                     exchange.set_markets(rest_instance.markets)
                                 else:
                                     await exchange.load_markets()
                             except:
                                 await exchange.load_markets()

                        candles = await exchange.watch_ohlcv(symbol, timeframe)
                        
                        backoff = 1 # Reset

                        if candles:
                            # La última vela suele ser la "actual en formación".
                            # La penúltima es la "recién cerrada".
                            # Estrategia: Enviamos la última para actualizar el precio actual,
                            # pero el BotService decidirá si es nueva.
                            latest_candle = candles[-1]
                            
                            event_data = {
                                "exchange": exchange_id,
                                "symbol": symbol,
                                "timeframe": timeframe,
                                "candle": {
                                    "timestamp": latest_candle[0], # Unix Timestamp ms
                                    "open": latest_candle[1],
                                    "high": latest_candle[2],
                                    "low": latest_candle[3],
                                    "close": latest_candle[4],
                                    "volume": latest_candle[5]
                                }
                            }
                            # Emitir evento específico de vela
                            await self.notify_listeners("candle_update", event_data)
                    except ccxt.NetworkError as ne:
                         logger.warning(f"Network error in candle stream {stream_key}: {ne}")
                         await asyncio.sleep(backoff)
                         backoff = min(backoff * 2, 60)
                    except Exception as e:
                         logger.error(f"Error in candle stream loop {stream_key}: {e}")
                         await asyncio.sleep(backoff)
                         backoff = min(backoff * 2, 60)
                        
            except Exception as e:
                logger.error(f"Fatal error in stream de velas {stream_key}: {e}")
                # Lógica de reconexión aquí...

        task = asyncio.create_task(candle_loop())
        task.set_name(stream_key)
        self.tasks.append(task)

