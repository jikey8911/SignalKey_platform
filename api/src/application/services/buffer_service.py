import pandas as pd
import logging
import asyncio
from typing import Dict, Optional, List
from datetime import datetime
from api.src.adapters.driven.exchange.stream_service import MarketStreamService
from api.src.application.services.cex_service import CEXService

logger = logging.getLogger(__name__)

class DataBufferService:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(DataBufferService, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self, stream_service: MarketStreamService = None, cex_service: CEXService = None):
        if self._initialized:
            return
            
        self.buffers: Dict[str, pd.DataFrame] = {} # Key: "exchange_symbol_timeframe"
        self.stream_service = stream_service or MarketStreamService()
        self.cex_service = cex_service or CEXService()
        self.lock = asyncio.Lock()
        
        # Subscribe to stream updates
        self.stream_service.add_listener(self.handle_stream_update)
        
        self._initialized = True

    def get_buffer_key(self, exchange_id: str, symbol: str, timeframe: str) -> str:
        return f"{exchange_id}_{symbol}_{timeframe}"

    async def initialize_buffer(self, exchange_id: str, symbol: str, timeframe: str = '15m', limit: int = 100):
        """Fetches initial history and sets up the buffer."""
        key = self.get_buffer_key(exchange_id, symbol, timeframe)
        
        async with self.lock:
            if key in self.buffers:
                return # Already initialized

            logger.info(f"Initializing buffer for {symbol} ({timeframe})")
            
            # 1. Fetch History via REST
            # Assuming CEXService has a method that returns DataFrame or list of OHLCV
            # Adapting to CEXService's get_historical_candles if available, or using ccxt adapter directly
            try:
                # Need user_id for API keys? Using default or system keys for public data usually defined in adapter
                # For Sprint 1, assuming public market data doesn't strictly need user keys for all exchanges 
                # or we pass a generic system user.
                # TODO: Refactor CEXService to allow public data fetch without user_id if possible
                candles = await self.cex_service.ccxt_adapter.fetch_ohlcv(
                    exchange_id=exchange_id, 
                    symbol=symbol, 
                    timeframe=timeframe, 
                    limit=limit
                )
                
                if candles:
                    df = pd.DataFrame(candles, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                    df.set_index('timestamp', inplace=True)
                    self.buffers[key] = df
                    logger.info(f"Buffer initialized for {key}: {len(df)} candles")
                else:
                    logger.warning(f"No history found for {key}")
                    
            except Exception as e:
                logger.error(f"Failed to initialize buffer for {key}: {e}")

    async def handle_stream_update(self, event_type: str, data: Dict):
        """Processes real-time updates from WebSocket."""
        # For Sprint 1, we might only have Ticker updates. 
        # Ideally we want KLine/Candle updates from WS.
        # If we only have Ticker, we update the "current" candle's close price in real-time.
        
        if event_type == "ticker_update":
            # Ticker update: {'exchange': 'binance', 'symbol': 'BTC/USDT', 'ticker': {...}}
             await self.update_with_ticker(data)

    async def update_with_ticker(self, data: Dict):
        exchange_id = data.get("exchange")
        symbol = data.get("symbol")
        ticker = data.get("ticker", {})
        price = ticker.get("last")
        timestamp = ticker.get("timestamp") # ms
        
        if not price or not timestamp:
            return

        # Update all timeframes for this symbol
        # This is a simplification. Real implementation needs candle boundaries logic.
        curr_time = pd.to_datetime(timestamp, unit='ms')
        
        async with self.lock:
            for key, df in self.buffers.items():
                if key.startswith(f"{exchange_id}_{symbol}_"):
                    # Logic: 
                    # 1. Check if current time belongs to the last candle
                    # 2. If yes, update Close, High, Low
                    # 3. If no (new candle), append new row
                    
                    if df.empty:
                        continue
                        
                    last_idx = df.index[-1]
                    # Simple check: If difference is small enough, it's same candle? 
                    # No, need explicit timeframe logic (e.g. 15m boundaries)
                    # For now, simplistic "update last" approach for responsiveness
                    
                    # Update High/Low
                    df.at[last_idx, 'close'] = price
                    if price > df.at[last_idx, 'high']:
                        df.at[last_idx, 'high'] = price
                    if price < df.at[last_idx, 'low']:
                        df.at[last_idx, 'low'] = price
                    
                    # Update Volume? Ticker volume is 24h usually, not candle volume. 
                    # Ignoring volume update from ticker for now.

    def get_latest_data(self, exchange_id: str, symbol: str, timeframe: str) -> Optional[pd.DataFrame]:
        key = self.get_buffer_key(exchange_id, symbol, timeframe)
        return self.buffers.get(key)
