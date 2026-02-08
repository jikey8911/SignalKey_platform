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
        self.public_instances = {} # Map: exchange_id -> instance
        self._exchange_instance = None # Legacy/System instance
        self._current_exchange_id = None
        
        # User-specific caching MULTI-EXCHANGE
        # Estructura: { user_id: { 'binance': instance, 'okx': instance } }
        self.user_instances: Dict[str, Dict[str, Any]] = {} 
    
    def _create_custom_session(self):
        """Creates an aiohttp session with ThreadedResolver to bypass Windows Async DNS issues"""
        try:
            resolver = ThreadedResolver()
            connector = aiohttp.TCPConnector(resolver=resolver, limit=100, force_close=False)
            return aiohttp.ClientSession(connector=connector)
        except Exception as e:
            logger.error(f"Error creating custom session: {e}")
            return None

    async def get_public_exchange_instance(self, exchange_id: str):
        """Método requerido por StreamService para obtener metadatos."""
        return await self._get_system_client_for_exchange(exchange_id)

    async def _get_client_for_user(self, user_id: str, exchange_id: Optional[str] = None):
        """Retrieves the exchange client for a specific user supporting multiple active exchanges."""
        try:
            # 1. Resolve Exchange ID if not provided
            config = None
            if not exchange_id:
                config = await get_app_config(user_id)
                exchange_id = "binance" # Default fallback
                if config:
                    if 'activeExchange' in config:
                         exchange_id = config['activeExchange']
                    elif 'exchanges' in config:
                        active_ex = next((e for e in config['exchanges'] if e.get('isActive')), None)
                        if active_ex:
                            exchange_id = active_ex['exchangeId']
            
            exchange_id = exchange_id.lower()

            # 2. Check Cache (Multi-level)
            if user_id not in self.user_instances:
                self.user_instances[user_id] = {}
            
            cached_instance = self.user_instances[user_id].get(exchange_id)
            
            if cached_instance:
                if cached_instance.session and cached_instance.session.closed:
                    logger.warning(f"⚠️ Session closed for {user_id} {exchange_id}, re-initializing...")
                else:
                    return cached_instance

            # 3. Initialization logic
            if not config:
                 config = await get_app_config(user_id)

            logger.info(f"🔌 Initializing User {user_id} Exchange Adapter for: {exchange_id.upper()}")
            
            exchange_class = getattr(ccxt, exchange_id)
            
            exchange_config = {
                'enableRateLimit': True,
                'options': {
                    'defaultType': 'spot',
                    'fetchCurrencies': False,
                    'adjustForTimeDifference': True
                }
            }
            
            # Extract credentials
            active_ex_config = None
            if config and 'exchanges' in config:
                 active_ex_config = next((e for e in config['exchanges'] if e.get('exchangeId') == exchange_id), None)
            
            if active_ex_config:
                if 'apiKey' in active_ex_config: exchange_config['apiKey'] = active_ex_config['apiKey']
                if 'secret' in active_ex_config: exchange_config['secret'] = active_ex_config['secret']
                if 'password' in active_ex_config: exchange_config['password'] = active_ex_config['password']
                if 'uid' in active_ex_config: exchange_config['uid'] = active_ex_config['uid']

            instance = exchange_class(exchange_config)
            
            session = self._create_custom_session()
            if session:
                instance.session = session
            
            if exchange_id == 'okx':
                instance.has['fetchCurrencies'] = False
            
            self.user_instances[user_id][exchange_id] = instance
            
            return instance
            
        except Exception as e:
            logger.error(f"Failed to initialize exchange client for user {user_id}: {e}")
            return await self._get_system_client()

    async def _get_system_client_for_exchange(self, exchange_id: str):
        """Retrieves a system-wide client for a specific exchange."""
        exchange_id = exchange_id.lower()

        if exchange_id in self.public_instances:
            inst = self.public_instances[exchange_id]
            if inst.session and not inst.session.closed:
                return inst

        exchange_class = getattr(ccxt, exchange_id)
        instance = exchange_class({
            'enableRateLimit': True,
            'options': {'defaultType': 'spot', 'fetchCurrencies': False}
        })

        session = self._create_custom_session()
        if session:
            instance.session = session

        if exchange_id == 'okx':
            instance.has['fetchCurrencies'] = False

        self.public_instances[exchange_id] = instance
        return instance

    async def _get_system_client(self):
        """Fallback Legacy System Client"""
        if not self._exchange_instance or (self._exchange_instance.session and self._exchange_instance.session.closed):
            return await self._get_system_client_for_exchange('binance')
        return self._exchange_instance

    # --- IExchangePort Implementation ---

    async def get_current_price(self, symbol: str, user_id: str) -> float:
        client = await self._get_client_for_user(user_id)
        ticker = await client.fetch_ticker(symbol)
        return ticker['last']

    async def get_public_current_price(self, symbol: str, exchange_id: str = "binance") -> float:
        client = await self._get_system_client_for_exchange(exchange_id)
        ticker = await client.fetch_ticker(symbol)
        return ticker['last']

    async def create_public_instance(self, exchange_id: str):
        return await self._get_system_client_for_exchange(exchange_id)

    async def fetch_balance(self, user_id: str, exchange_id: Optional[str] = None) -> List[Balance]:
        try:
             client = await self._get_client_for_user(user_id, exchange_id)
             if not client: return []

             balance_data = await client.fetch_balance()
             balances = []
             if 'total' in balance_data:
                 for asset, total in balance_data['total'].items():
                     if total > 0:
                         free = balance_data['free'].get(asset, 0.0)
                         used = balance_data['used'].get(asset, 0.0)
                         balances.append(Balance(asset=asset, free=free, used=used, total=total))
             return balances
        except Exception as e:
            logger.error(f"Error fetching balance for user {user_id}: {e}")
            return []

    async def create_order(self, user_id: str, exchange_id: str, symbol: str, type: str, side: str, amount: float, price: float = None, params: Dict = {}) -> TradeResult:
        try:
            client = await self._get_client_for_user(user_id, exchange_id=exchange_id)
            if not client:
                 return TradeResult(success=False, message=f"Could not initialize exchange client for user {user_id}")

            logger.info(f"🚀 Creating Order: {side.upper()} {symbol} Amt:{amount} via {client.id}")
            order = await client.create_order(symbol, type, side, amount, price, params)
            
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
        symbol = analysis.symbol
        side = analysis.decision.lower() if hasattr(analysis.decision, 'lower') else str(analysis.decision).lower()
        amount = analysis.parameters.amount
        if not amount: return TradeResult(success=False, message="Amount is zero")
        return await self.create_order(user_id, exchange_id, symbol, 'market', side, amount)

    # --- MISSING METHODS IMPLEMENTATION ---

    async def fetch_open_orders(self, user_id: str, symbol: Optional[str] = None) -> List[Order]:
        """Fetches open orders for a user."""
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
        if user_id and user_id != "default_user":
            client = await self._get_client_for_user(user_id, exchange_id=exchange_id)
        elif exchange_id:
            client = await self._get_system_client_for_exchange(exchange_id)
        else:
            client = await self._get_system_client()
        
        if use_random_date:
            max_days_back = 730
            min_days_back = 365
            random_offset = random.randint(min_days_back, max_days_back)
            end_date = datetime.utcnow() - timedelta(days=random_offset)
            since_dt = end_date - timedelta(hours=limit) 
            since_ts = int(since_dt.timestamp() * 1000)
        else:
            since_ts = None 

        ohlcv = await client.fetch_ohlcv(symbol, timeframe, since=since_ts, limit=limit)
        
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df.set_index('timestamp', inplace=True)
        return df

    async def get_public_historical_data(self, symbol: str, timeframe: str, limit: int = 1500, use_random_date: bool = False, exchange_id: str = None, user_id: str = None) -> pd.DataFrame:
        """
        Public API fetcher required by ML Service and Backtesting.
        Does not require user authentication.
        """
        target_exchange = exchange_id if exchange_id else "binance"
        # Force use of system client or public instance (no user_id needed really, but kept signature)
        return await self.get_historical_data(
            symbol, timeframe, limit, use_random_date, user_id=None, exchange_id=target_exchange
        )

    async def get_markets(self, exchange_id: str) -> List[str]:
        """
        Returns available market types (spot, swap, future, etc.) for an exchange.
        """
        try:
            client = await self._get_system_client_for_exchange(exchange_id)
            await client.load_markets()
            
            # Extract underlying market types
            market_types = set()
            for key, market in client.markets.items():
                m_type = market.get('type')
                if m_type:
                    market_types.add(m_type)
            
            return sorted(list(market_types))
        except Exception as e:
            logger.error(f"Error fetching markets for {exchange_id}: {e}")
            return []

    async def get_symbols(self, exchange_id: str, market_type: str) -> List[str]:
        """
        Returns active symbols for a specific market type on an exchange.
        """
        try:
            client = await self._get_system_client_for_exchange(exchange_id)
            await client.load_markets()
            
            symbols = []
            for symbol, market in client.markets.items():
                if market.get('type') == market_type and market.get('active', True):
                    symbols.append(symbol)
            
            return sorted(symbols)
        except Exception as e:
            logger.error(f"Error fetching symbols for {exchange_id} ({market_type}): {e}")
            return []

    # --- END MISSING METHODS ---

    async def close_all(self):
        """Close ALL managed instances properly."""
        # Close System Instances
        for ex_id, instance in self.public_instances.items():
            try:
                if instance.session: await instance.session.close()
                await instance.close()
            except: pass
        self.public_instances.clear()
            
        # Close User Instances
        for user_id, exchanges in self.user_instances.items():
            for ex_id, instance in exchanges.items():
                try:
                    if instance.session: await instance.session.close()
                    await instance.close()
                except Exception as e:
                    logger.error(f"Error closing exchange {ex_id} for user {user_id}: {e}")
        self.user_instances.clear()

CCXTService = CcxtAdapter 
ccxt_service = CCXTService()