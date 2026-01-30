import ccxt.async_support as ccxt
import logging
import aiohttp
import pandas as pd
from aiohttp.resolver import ThreadedResolver
from typing import Optional, Dict, Any, Tuple, List
from datetime import datetime, timedelta
import random

# Import Interface
from api.src.domain.services.exchange_port import IExchangePort
from api.src.domain.entities.trading import Balance, Order, TradeResult, Ticker
from api.src.domain.entities.signal import SignalAnalysis
from api.src.adapters.driven.persistence.mongodb import get_app_config

logger = logging.getLogger(__name__)

class CcxtAdapter(IExchangePort):
    def __init__(self, db_adapter=None):
        self.db = db_adapter
        self.public_instances = {}
        self._exchange_instance = None # Legacy/System instance
        self._current_exchange_id = None
        
        # User-specific caching
        self.user_instances = {} # Map: user_id -> ccxt_instance
        self.user_exchange_ids = {} # Map: user_id -> exchange_id (to detect changes)
    
    def _create_custom_session(self):
        """Creates an aiohttp session with ThreadedResolver to bypass Windows Async DNS issues"""
        try:
            resolver = ThreadedResolver()
            connector = aiohttp.TCPConnector(resolver=resolver)
            return aiohttp.ClientSession(connector=connector)
        except Exception as e:
            logger.error(f"Error creating custom session: {e}")
            return None

    async def _get_client_for_user(self, user_id: str):
        """
        Retrieves the active exchange for a specific user and initializes/returns the CCXT client.
        Caches the client for subsequent calls.
        """
        try:
            # 1. Fetch user config
            exchange_id = "binance" # Default
            config = await get_app_config(user_id)
            
            if config:
                # Look for 'active_exchange' or fallback to specific exchange status logic if needed
                # Ideally, we should add 'activeExchange' to user config schema or infer it.
                # For now, let's assume valid 'active_exchange' key in config or simple logic.
                # Assuming schema: config['activeExchange'] = 'okx' OR checking 'exchanges' list
                if 'activeExchange' in config:
                     exchange_id = config['activeExchange']
                elif 'exchanges' in config:
                    # Find first active exchange
                    active_ex = next((e for e in config['exchanges'] if e.get('isActive')), None)
                    if active_ex:
                        exchange_id = active_ex['exchangeId']
            
            # 2. Check Cache
            cached_exchange_id = self.user_exchange_ids.get(user_id)
            cached_instance = self.user_instances.get(user_id)
            
            if cached_instance and cached_exchange_id == exchange_id:
                return cached_instance

            # 3. Switching or New Initialization
            logger.info(f"🔄 Switching/Init User {user_id} Exchange Adapter to: {exchange_id.upper()}")
            
            # Close previous if exists
            if cached_instance:
                await cached_instance.close()

            # Initialize new client
            exchange_class = getattr(ccxt, exchange_id)
            # Potentially load API keys here if private access needed
            # For now, public instance as per previous implementation logic, but scoped to user preference
            instance = exchange_class({
                'enableRateLimit': True,
                'options': {
                    'defaultType': 'spot',
                    'fetchCurrencies': False
                }
            })
            
            # Apply Windows DNS Fix
            session = self._create_custom_session()
            if session:
                instance.session = session
            
            # OKX Specifics
            if exchange_id == 'okx':
                instance.has['fetchCurrencies'] = False
            
            # Update Cache
            self.user_instances[user_id] = instance
            self.user_exchange_ids[user_id] = exchange_id
            
            return instance
            
        except Exception as e:
            logger.error(f"Failed to initialize exchange client for user {user_id}: {e}")
            # Fallback to generic binance instance (not cached per user to save resources)
            return await self._get_system_client()

    async def _get_system_client(self):
        """
        Retrieves the system-wide default exchange (fallback).
        """
        # ... (Legacy system client logic remains as fallback)
        try:
            # 1. Fetch active exchange from DB (System Global Config - if separate collection exists or reuse)
            # NOTE: User requested User-Aware loading. System client might just be a default "Binance"
            # or reading a global admin config. Let's keep existing logic but careful with 'self.db' usage.
            exchange_id = "binance" # Default
            if self.db:
                # Assuming 'app_configs' might also hold global configs with special key?
                # Or just fallback to binance. 
                # Preserving existing logic for now:
                config = await self.db.app_configs.find_one({"key": "active_exchange"})
                if config and 'value' in config:
                    exchange_id = config['value']
            
            # 2. Check if re-initialization is needed
            if not self._exchange_instance or self._current_exchange_id != exchange_id:
                logger.info(f"🔄 Switching System Exchange Adapter to: {exchange_id.upper()}")
                
                # Close previous if exists
                if self._exchange_instance:
                    await self._exchange_instance.close()

                # Initialize new client
                exchange_class = getattr(ccxt, exchange_id)
                self._exchange_instance = exchange_class({
                    'enableRateLimit': True,
                    'options': {
                        'defaultType': 'spot',
                        'fetchCurrencies': False
                    }
                })
                
                # Apply Windows DNS Fix
                session = self._create_custom_session()
                if session:
                    self._exchange_instance.session = session
                
                # OKX Specifics
                if exchange_id == 'okx':
                    self._exchange_instance.has['fetchCurrencies'] = False
                
                self._current_exchange_id = exchange_id
                
            return self._exchange_instance
            
        except Exception as e:
            logger.error(f"Failed to initialize system exchange client: {e}")
            if not self._exchange_instance:
                 self._exchange_instance = ccxt.binance({'enableRateLimit': True})
            return self._exchange_instance

    # --- IExchangePort Implementation ---

    async def get_current_price(self, symbol: str, user_id: str) -> float:
        """Get the current price of a symbol using the system's active exchange."""
        client = await self._get_system_client()
        ticker = await client.fetch_ticker(symbol)
        return ticker['last']

    async def fetch_balance(self, user_id: str, exchange_id: Optional[str] = None) -> List[Balance]:
        """
        Fetch balance. If exchange_id is provided (User specific), it creates a temporary private instance.
        If not, it attempts to use the system client (though fetching balance usually requires private auth).
        """
        # Note: This method signature implies resolving API keys for the user.
        # For this refactor, we will focus on the public/system methods first as requested.
        # Private methods usually require passing API keys explicitly or resolving them via User Service.
        pass 

    async def execute_trade(self, analysis: SignalAnalysis, user_id: str) -> TradeResult:
        pass # To be implemented via private instance logic

    async def fetch_open_orders(self, user_id: str, symbol: Optional[str] = None) -> List[Order]:
        pass # To be implemented

    async def get_historical_data(self, symbol: str, timeframe: str, limit: int = 1500, use_random_date: bool = False, user_id: str = "default_user") -> pd.DataFrame:
        """
        Fetch historical data using the user's preferred exchange.
        """
        if user_id and user_id != "default_user":
            client = await self._get_client_for_user(user_id)
        else:
            client = await self._get_system_client()
        
        # Calculate start time
        if use_random_date:
            max_days_back = 730
            min_days_back = 365
            random_offset = random.randint(min_days_back, max_days_back)
            end_date = datetime.utcnow() - timedelta(days=random_offset)
            # Fetch enough data for 'limit' candles (rough approx)
            # Assuming timeframe 1h for now or using limit param directly
            since_dt = end_date - timedelta(hours=limit) 
            logger.info(f"🎲 Random training period ending: {end_date.strftime('%Y-%m-%d')}")
            since_ts = int(since_dt.timestamp() * 1000)
        else:
            since_ts = None # Fetch most recent

        ohlcv = await client.fetch_ohlcv(symbol, timeframe, since=since_ts, limit=limit)
        
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df.set_index('timestamp', inplace=True)
        return df

    # --- Legacy / Helper Methods (kept for compatibility during transition) ---

    async def get_historical_ohlcv(self, symbol: str, exchange_id: str = None, timeframe: str = '1h', days_back: int = 365, use_random_date: bool = False) -> list:
        """
        Legacy wrapper to maintain compatibility with existing MLService calls 
        until they are fully refactored to use generic `get_historical_data`.
        """
        # If exchange_id is explicitly passed, we unfortunately have to respect it or ignore it.
        # For the "Dynamic" goal, we should prefer the system client if exchange_id matches dynamic one.
        client = await self._get_system_client()
        
        # Reuse logic from get_historical_data but return raw list as expected by legacy
        # ... (Duplicate logic for robustness during transition)
        # For simplicity, let's call the new method and convert back to list
        try:
             # Calculate limit based on days_back approx (e.g. 1h candles)
             limit = days_back * 24 
             df = await self.get_historical_data(symbol, timeframe, limit=limit, use_random_date=use_random_date)
             
             # Convert back to list of lists: [timestamp_ms, open, high, low, close, volume]
             # Reset index to get timestamp as column
             df_reset = df.reset_index()
             # Convert timestamp back to ms int
             df_reset['timestamp'] = df_reset['timestamp'].astype('int64') // 10**6
             return df_reset[['timestamp', 'open', 'high', 'low', 'close', 'volume']].values.tolist()
        except Exception as e:
            logger.error(f"Error in legacy get_historical_ohlcv: {e}")
            return []

    async def get_markets(self, exchange_id: str) -> List[str]:
        """
        Retrieves available market types (spot, swap, future, margin) for a given exchange.
        """
        exchange_id = exchange_id.lower()
        try:
            # If requesting the currently active system exchange, reuse it
            if self._exchange_instance and self._current_exchange_id == exchange_id:
                if not self._exchange_instance.markets:
                    await self._exchange_instance.load_markets()
                markets = self._exchange_instance.markets
            else:
                # Create temporary instance for metadata fetching
                markets = await self._fetch_markets_temp(exchange_id)

            if not markets:
                return []

            # Extract unique types
            types = set()
            for symbol, info in markets.items():
                if info.get('active'):
                    # CCXT standarizes types: spot, swap, future, margin, option
                    m_type = info.get('type')
                    if info.get('spot'): m_type = 'spot' 
                    if info.get('swap'): m_type = 'swap'
                    if info.get('future'): m_type = 'future'
                    if m_type:
                        types.add(m_type)
            
            return list(types)
        except Exception as e:
            logger.error(f"Error getting markets for {exchange_id}: {e}")
            return []

    async def get_symbols(self, exchange_id: str, market_type: str) -> List[str]:
        """
        Retrieves active symbols for a specific exchange and market type.
        """
        exchange_id = exchange_id.lower()
        try:
            # Reuse system instance if possible
            if self._exchange_instance and self._current_exchange_id == exchange_id:
                if not self._exchange_instance.markets:
                    await self._exchange_instance.load_markets()
                markets = self._exchange_instance.markets
            else:
                markets = await self._fetch_markets_temp(exchange_id)

            if not markets:
                return []

            symbols = []
            for symbol, info in markets.items():
                is_active = info.get('active')
                m_type = info.get('type')
                
                # Normalizar tipos si es necesario (algunos exchanges usan flags booleanos)
                if info.get('spot'): m_type = 'spot'
                if info.get('swap'): m_type = 'swap'
                if info.get('future'): m_type = 'future'

                if is_active and m_type == market_type:
                    symbols.append(symbol)
            
            return sorted(symbols)
        except Exception as e:
            logger.error(f"Error getting symbols for {exchange_id} {market_type}: {e}")
            return []

    async def _fetch_markets_temp(self, exchange_id: str) -> Dict:
        """Helper to fetch markets using a temporary instance."""
        exchange_id = exchange_id.lower()
        try:
            ex_class = getattr(ccxt, exchange_id)
            async with ex_class() as inst:
                session = self._create_custom_session()
                if session: inst.session = session
                
                # Optimize loading if possible (some exchanges support fetching only markets)
                return await inst.load_markets()
        except Exception as e:
            logger.error(f"Error fetching markets temp for {exchange_id}: {e}")
            return {}

    async def close_all(self):
        if self._exchange_instance:
            await self._exchange_instance.close()

# Alias for backward compatibility if needed, 
# though we will change main.py to use `CcxtAdapter`
CCXTService = CcxtAdapter 

# Global instance for backward compatibility and default imports
ccxt_service = CCXTService()
