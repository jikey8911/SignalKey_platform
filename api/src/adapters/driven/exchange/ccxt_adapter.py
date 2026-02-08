import ccxt.async_support as ccxt
import logging
import aiohttp
import asyncio
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

    async def _get_client_for_user(self, user_id: str, exchange_id: Optional[str] = None):
        """
        Retrieves the exchange client for a specific user.
        If exchange_id is not provided, it uses the user's active exchange.
        Caches the client for subsequent calls.
        """
        try:
            # 1. Fetch user config
            config = await get_app_config(user_id)
            
            if not exchange_id:
                exchange_id = "binance" # Default
                if config:
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
            
            # Prepare configuration with API Keys
            exchange_config = {
                'enableRateLimit': True,
                'options': {
                    'defaultType': 'spot',
                    'fetchCurrencies': False
                }
            }
            
            # Extract credentials if available in the matched config
            active_ex_config = None
            if config and 'exchanges' in config:
                 # Find the specific config object for this exchange_id
                 active_ex_config = next((e for e in config['exchanges'] if e.get('exchangeId') == exchange_id), None)
            
            if active_ex_config:
                if 'apiKey' in active_ex_config: exchange_config['apiKey'] = active_ex_config['apiKey']
                if 'secret' in active_ex_config: exchange_config['secret'] = active_ex_config['secret']
                if 'password' in active_ex_config: exchange_config['password'] = active_ex_config['password']
                if 'uid' in active_ex_config: exchange_config['uid'] = active_ex_config['uid']
                logger.info(f"🔑 Loaded credentials for {exchange_id} (User {user_id})")

            instance = exchange_class(exchange_config)
            
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

    async def _get_system_client_for_exchange(self, exchange_id: str):
        """
        Retrieves a system-wide client for a specific exchange.
        Uses a separate cache for system instances.
        """
        exchange_id = exchange_id.lower()

        # 1. Check if we already have a public/system instance for this exchange
        if exchange_id in self.public_instances:
            return self.public_instances[exchange_id]

        # 2. Initialize new system-wide client for this exchange
        logger.info(f"🔄 Initializing System Exchange Adapter for: {exchange_id.upper()}")

        exchange_class = getattr(ccxt, exchange_id)
        instance = exchange_class({
            'enableRateLimit': True,
            'options': {
                'defaultType': 'spot',
                'fetchCurrencies': False
            }
        })

        session = self._create_custom_session()
        if session:
            instance.session = session

        if exchange_id == 'okx':
            instance.has['fetchCurrencies'] = False

        # Update Cache
        self.public_instances[exchange_id] = instance
        return instance

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
        """Get the current price of a symbol using the user's configured exchange."""
        # Fix: Use user specific client to respect active exchange
        client = await self._get_client_for_user(user_id)
        ticker = await client.fetch_ticker(symbol)
        return ticker['last']

    async def create_public_instance(self, exchange_id: str):
        """Create a public instance for CEXService support"""
        try:
            exchange_class = getattr(ccxt, exchange_id.lower())
            instance = exchange_class({
                'enableRateLimit': True,
                'options': {'defaultType': 'spot', 'fetchCurrencies': False}
            })
            session = self._create_custom_session()
            if session: instance.session = session
            if exchange_id.lower() == 'okx': instance.has['fetchCurrencies'] = False
            return instance
        except Exception as e:
            logger.error(f"Error creating public instance {exchange_id}: {e}")
            return None

    async def get_private_instance(self, exchange_id: str, api_key: str, secret: str, password: str = None, uid: str = None):
        """Create a private instance matching CEXService expectations"""
        try:
            exchange_class = getattr(ccxt, exchange_id.lower())
            config = {
                'apiKey': api_key,
                'secret': secret,
                'enableRateLimit': True,
                'options': {'defaultType': 'spot'}
            }
            if password: config['password'] = password
            if uid: config['uid'] = uid
            
            instance = exchange_class(config)
            session = self._create_custom_session()
            if session: instance.session = session
            return instance
        except Exception as e:
             logger.error(f"Error creating private instance {exchange_id}: {e}")
             return None

    async def fetch_balance(self, user_id: str, exchange_id: Optional[str] = None) -> List[Balance]:
        """
        Fetch balance. If exchange_id is provided (User specific), it creates a temporary private instance.
        If not, it attempts to use the system client (though fetching balance usually requires private auth).
        """
        try:
             client = await self._get_client_for_user(user_id, exchange_id)
             if not client: return []

             balance_data = await client.fetch_balance()

             # Convert to List[Balance]
             balances = []
             if 'total' in balance_data:
                 for asset, total in balance_data['total'].items():
                     # Incluir balances positivos
                     if total > 0:
                         free = balance_data['free'].get(asset, 0.0)
                         used = balance_data['used'].get(asset, 0.0)
                         balances.append(Balance(asset=asset, free=free, used=used, total=total))
             return balances
        except Exception as e:
            logger.error(f"Error fetching balance for user {user_id}: {e}")
            return []

    async def create_order(self, user_id: str, exchange_id: str, symbol: str, type: str, side: str, amount: float, price: float = None, params: Dict = {}) -> TradeResult:
        """
        Wrapper directo para ccxt.create_order, resolviendo el cliente del usuario.
        """
        try:
            client = await self._get_client_for_user(user_id, exchange_id=exchange_id)
            if not client:
                 return TradeResult(success=False, message=f"Could not initialize exchange client for user {user_id}")

            logger.info(f"🚀 Creating Order: {side.upper()} {symbol} Amt:{amount} via {client.id} (Params: {params})")

            order = await client.create_order(
                symbol=symbol,
                type=type,
                side=side,
                amount=amount,
                price=price,
                params=params
            )

            # Extraer precio promedio
            avg_price = order.get('average') or order.get('price')
            if not avg_price and order.get('fills'):
                total_cost = sum(f['price'] * f['amount'] for f in order['fills'])
                total_qty = sum(f['amount'] for f in order['fills'])
                avg_price = total_cost / total_qty if total_qty > 0 else 0

            return TradeResult(
                success=True,
                message="Order executed successfully",
                order_id=order['id'],
                price=avg_price,
                amount=order['amount'],
                timestamp=datetime.utcnow(),
                details=order
            )
        except Exception as e:
            logger.error(f"Error creating order {symbol}: {e}")
            return TradeResult(success=False, message=str(e), error=str(e))

    async def execute_trade(self, analysis: SignalAnalysis, user_id: str, exchange_id: Optional[str] = None) -> TradeResult:
        """
        Ejecuta una operación en el exchange configurado para el usuario/bot.
        Delega en create_order.
        """
        symbol = analysis.symbol
        side = analysis.decision.lower() if hasattr(analysis.decision, 'lower') else str(analysis.decision).lower()
        amount = analysis.parameters.amount

        if not amount:
             return TradeResult(success=False, message="Amount is zero")

        return await self.create_order(user_id, exchange_id, symbol, 'market', side, amount)

    async def fetch_open_orders(self, user_id: str, symbol: Optional[str] = None) -> List[Order]:
        try:
            client = await self._get_client_for_user(user_id)
            orders = await client.fetch_open_orders(symbol)
            return [Order(
                id=o['id'],
                symbol=o['symbol'],
                type=o['type'],
                side=o['side'],
                amount=o['amount'],
                price=o['price'],
                status=o['status']
            ) for o in orders]
        except Exception as e:
             logger.error(f"Error fetching open orders for {user_id}: {e}")
             return []

    async def get_historical_data(self, symbol: str, timeframe: str, limit: int = 1500, use_random_date: bool = False, user_id: str = "default_user", exchange_id: Optional[str] = None) -> pd.DataFrame:
        """
        Fetch historical data using the user's preferred exchange or a specific one.
        """
        if user_id and user_id != "default_user":
            client = await self._get_client_for_user(user_id, exchange_id=exchange_id)
        elif exchange_id:
            # System-wide but specific exchange
            # (Note: we don't have a specific cache for this yet, so it might re-init system client)
            # For simplicity, we can use _get_system_client logic or just create a temporary one
            # Given this is for backtesting, performance is less critical than correctness
            client = await self._get_system_client_for_exchange(exchange_id)
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

    async def get_public_historical_data(self, symbol: str, timeframe: str, limit: int = 1500, use_random_date: bool = False, exchange_id: str = None, user_id: str = None) -> pd.DataFrame:
        """
        Fetch historical data using PUBLIC API (no credentials required).
        This method creates a temporary public-only connection for fetching OHLCV data.
        Ideal for ML training where authentication is not needed.
        
        Args:
            symbol: Trading pair symbol (e.g., 'BTC/USDT')
            timeframe: Candle timeframe (e.g., '1h', '4h', '1d')
            limit: Number of candles to fetch
            use_random_date: If True, fetches data from a random historical period
            exchange_id: Exchange to use (optional, overrides user config)
            user_id: User ID to resolve active exchange from (optional)
        
        Returns:
            DataFrame with OHLCV data
        """
        try:
            # Resolve Exchange ID
            if not exchange_id:
                if user_id:
                    # Attempt to resolve from user config
                    try:
                        config = await get_app_config(user_id)
                        if config:
                            if 'activeExchange' in config:
                                exchange_id = config['activeExchange']
                            elif 'exchanges' in config:
                                active_ex = next((e for e in config['exchanges'] if e.get('isActive')), None)
                                if active_ex:
                                    exchange_id = active_ex['exchangeId']
                    except Exception as e:
                        logger.warning(f"Could not resolve exchange for user {user_id}: {e}")
                
                # Default fallback if still None
                if not exchange_id:
                    exchange_id = "okx"

            # Create temporary public instance
            exchange_class = getattr(ccxt, exchange_id.lower())
            public_instance = exchange_class({
                'enableRateLimit': True,
                'options': {
                    'defaultType': 'spot',
                    'fetchCurrencies': False
                }
            })
            
            # Apply Windows DNS Fix
            session = self._create_custom_session()
            if session:
                public_instance.session = session
            
            # OKX Specifics
            if exchange_id.lower() == 'okx':
                public_instance.has['fetchCurrencies'] = False
            
            try:
                # Basic Timeframe parsing (seconds)
                tf_units = {'s': 1, 'm': 60, 'h': 3600, 'd': 86400, 'w': 604800}
                unit = timeframe[-1]
                val = int(timeframe[:-1]) if timeframe[:-1].isdigit() else 1
                duration_sec = val * tf_units.get(unit, 60)
                duration_ms = duration_sec * 1000

                # Calculate start time (since)
                if use_random_date:
                    max_days_back = 730
                    min_days_back = 365
                    random_offset = random.randint(min_days_back, max_days_back)
                    end_date = datetime.utcnow() - timedelta(days=random_offset)
                    since_dt = end_date - timedelta(seconds=limit * duration_sec)
                    logger.info(f"🎲 Public API: Random training period ending: {end_date.strftime('%Y-%m-%d')}")
                    start_ts = int(since_dt.timestamp() * 1000)
                else:
                    # Backwards capability: Calculate 'since' to get exactly 'limit' candles up to now
                    now = datetime.utcnow()
                    since_dt = now - timedelta(seconds=limit * duration_sec)
                    start_ts = int(since_dt.timestamp() * 1000)

                all_ohlcv = []
                current_since = start_ts
                
                # Pagination Loop
                # We fetch in chunks (e.g. 1000 which is safe for most exchanges)
                # until we have enough data or reach now
                FETCH_LIMIT = 1000 
                
                while len(all_ohlcv) < limit:
                    # Calculate how many needed
                    remaining = limit - len(all_ohlcv)
                    # Don't ask for more than safe limit
                    batch_limit = min(remaining, FETCH_LIMIT)
                    
                    # Fetch
                    ohlcv = await public_instance.fetch_ohlcv(symbol, timeframe, since=current_since, limit=batch_limit)
                    
                    if not ohlcv:
                        break
                        
                    all_ohlcv.extend(ohlcv)
                    
                    # Update since for next batch: last candle time + duration
                    last_time = ohlcv[-1][0]
                    current_since = last_time + duration_ms
                    
                    # Safety break if we reached current time (approx)
                    if current_since > datetime.utcnow().timestamp() * 1000:
                        break
                        
                    # Standard exchange rate limit protection
                    await asyncio.sleep(public_instance.rateLimit / 1000.0 if public_instance.rateLimit else 0.1)

                # Convert to DataFrame
                df = pd.DataFrame(all_ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                if not df.empty:
                    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                    df.set_index('timestamp', inplace=True)
                    # Remove duplicates just in case
                    df = df[~df.index.duplicated(keep='first')]
                
                logger.info(f"✅ Public API: Fetched {len(df)} candles for {symbol} from {exchange_id} (Requested: {limit})")
                return df
                
            finally:
                # Always close the temporary instance
                await public_instance.close()
                
        except Exception as e:
            logger.error(f"❌ Public API: Error fetching data for {symbol} from {exchange_id}: {e}")
            # Return empty DataFrame on error
            return pd.DataFrame(columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])

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

    async def test_connection_private(self, exchange_id: str, api_key: str, secret: str, password: str = None, uid: str = None) -> bool:
        """
        Tests connection with provided credentials.
        """
        exchange_id = exchange_id.lower()
        client = None
        try:
            exchange_class = getattr(ccxt, exchange_id)
            config = {
                'apiKey': api_key,
                'secret': secret,
                'enableRateLimit': True,
                'options': {'defaultType': 'spot'}
            }
            if password:
                config['password'] = password
            if uid: 
                 config['uid'] = uid
            
            client = exchange_class(config)
            
            # Windows DNS Fix
            session = self._create_custom_session()
            if session: client.session = session
            
            # Try a private endpoint (fetch_balance is usually good)
            await client.fetch_balance()
            return True
        except Exception as e:
            logger.error(f"Test connection failed for {exchange_id}: {e}")
            return False
        finally:
             if client:
                 await client.close()

    async def fetch_balance_private(self, exchange_id: str, api_key: str, secret: str, password: str = None, uid: str = None) -> Dict[str, Any]:
        """
        Fetches balance using provided credentials directly (without persistent user referencing).
        Useful for one-off checks or when CEXService manages the credentials.
        """
        exchange_id = exchange_id.lower()
        client = None
        try:
            exchange_class = getattr(ccxt, exchange_id)
            config = {
                'apiKey': api_key,
                'secret': secret,
                'enableRateLimit': True,
                'options': {'defaultType': 'spot'}
            }
            if password:
                config['password'] = password
            if uid: 
                 config['uid'] = uid
            
            client = exchange_class(config)
            
            # Windows DNS Fix
            session = self._create_custom_session()
            if session: client.session = session
            
            balance = await client.fetch_balance()
            return balance
        except Exception as e:
            logger.error(f"Error fetching private balance for {exchange_id}: {e}")
            return {}
        finally:
            if client:
                await client.close()

    async def close_all(self):
        """Close ALL managed instances: System, User-Specific, and Legacy."""
        # 1. Close system instance
        if self._exchange_instance:
            try:
                await self._exchange_instance.close()
            except: pass

        # 2. Close public instances
        for instance in self.public_instances.values():
            try:
                await instance.close()
            except: pass
            
        # 3. Close user-specific instances (CRITICAL for multi-exchange support)
        for user_id, instance in self.user_instances.items():
            try:
                await instance.close()
            except Exception as e:
                logger.error(f"Error closing exchange for user {user_id}: {e}")
        
        # Clear caches
        self.public_instances = {}
        self.user_instances = {}
        self.user_exchange_ids = {}
        self._exchange_instance = None

# Alias for backward compatibility if needed, 
# though we will change main.py to use `CcxtAdapter`
CCXTService = CcxtAdapter 

# Global instance for backward compatibility and default imports
ccxt_service = CCXTService()
