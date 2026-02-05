import asyncio
import logging
from typing import Dict, Any, Callable, List, Optional
import ccxt.pro as ccxt

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
        while self.running:
            try:
                # This await blocks until update is received
                ticker = await exchange.watch_ticker(symbol)
                
                # Emit event
                await self.notify_listeners("ticker_update", {
                    "exchange": exchange.id,
                    "symbol": symbol,
                    "ticker": ticker
                })
            except ccxt.NetworkError as e:
                logger.warning(f"Network error watching {symbol} on {exchange.id}: {e}. Retrying in 5s..")
                await asyncio.sleep(5)
            except Exception as e:
                logger.error(f"Error watching {symbol} on {exchange.id}: {e}")
                await asyncio.sleep(5) # Prevent tight loop on error
