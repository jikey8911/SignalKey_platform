import asyncio
import logging
import ccxt.pro as ccxtpro
from typing import Dict, Any, Optional, AsyncGenerator, List
import pandas as pd
from datetime import datetime

logger = logging.getLogger("CCXTAdapter")

class CcxtAdapter:
    """
    Adaptador para CCXT Pro.
    Centraliza conexiones WebSocket (watch) y peticiones REST (fetch/execute).
    """
    def __init__(self, **kwargs):
        self.exchanges: Dict[str, ccxtpro.Exchange] = {}
        self._locks: Dict[str, asyncio.Lock] = {}
        self.db = kwargs.get('db_adapter')

    async def _get_exchange(self, exchange_id: str, user_id: str = None) -> ccxtpro.Exchange:
        """
        Obtiene una instancia de exchange. Si se provee user_id, intenta cargar credenciales.
        """
        eid = exchange_id.lower()
        instance_key = f"{eid}:{user_id}" if user_id else eid
        
        if instance_key not in self._locks:
            self._locks[instance_key] = asyncio.Lock()
            
        async with self._locks[instance_key]:
            if instance_key not in self.exchanges:
                # 1. Configuración Base
                config = {
                    'enableRateLimit': True,
                    'options': {
                        'defaultType': 'spot',
                        'fetchCurrencies': False
                    }
                }

                # 2. Cargar Credenciales si hay usuario
                if user_id:
                    try:
                        # Importación diferida para evitar ciclos
                        from api.src.adapters.driven.persistence.mongodb import get_app_config
                        user_config = await get_app_config(user_id)
                        
                        if user_config and "exchanges" in user_config:
                            # Buscar configuración para este exchange específico
                            exchange_conf = next((e for e in user_config["exchanges"] 
                                                if e.get("exchangeId") == eid and e.get("isActive", True)), None)
                            
                            if exchange_conf:
                                if exchange_conf.get('apiKey'):
                                    config['apiKey'] = exchange_conf.get('apiKey')
                                if exchange_conf.get('secret'):
                                    config['secret'] = exchange_conf.get('secret')
                                if exchange_conf.get('password'):
                                    config['password'] = exchange_conf.get('password')
                                if exchange_conf.get('uid'):
                                    config['uid'] = exchange_conf.get('uid')
                                
                                # Ajustar tipo de mercado si está configurado
                                if exchange_conf.get('marketType'):
                                    config['options']['defaultType'] = exchange_conf.get('marketType')
                                    
                    except Exception as e:
                        logger.warning(f"No se pudieron cargar credenciales para {user_id} en {eid}: {e}")

                # 3. Instanciar
                try:
                    exchange_class = getattr(ccxtpro, eid)
                    self.exchanges[instance_key] = exchange_class(config)
                except AttributeError:
                    logger.error(f"Exchange {eid} no soportado por CCXT Pro")
                    raise ValueError(f"Exchange {eid} not supported")

            return self.exchanges[instance_key]

    # --- WEBSOCKETS (EVENT-DRIVEN) ---

    async def watch_ticker(self, exchange_id: str, symbol: str) -> AsyncGenerator[Dict[str, Any], None]:
        exchange = await self._get_exchange(exchange_id)
        while True:
            try:
                ticker = await exchange.watch_ticker(symbol)
                yield ticker
            except Exception as e:
                logger.error(f"Error WS Ticker ({exchange_id}:{symbol}): {e}")
                await asyncio.sleep(10)

    async def watch_ohlcv(self, exchange_id: str, symbol: str, timeframe: str) -> AsyncGenerator[list, None]:
        exchange = await self._get_exchange(exchange_id)
        while True:
            try:
                ohlcv = await exchange.watch_ohlcv(symbol, timeframe)
                if ohlcv:
                    yield ohlcv
            except Exception as e:
                logger.error(f"Error WS OHLCV ({exchange_id}:{symbol}:{timeframe}): {e}")
                await asyncio.sleep(10)

    # --- REST METHODS ---

    async def execute_trade(self, symbol: str, side: str, amount: float, price: Optional[float] = None, user_id: str = None, exchange_id: str = 'binance') -> Dict[str, Any]:
        exchange = await self._get_exchange(exchange_id, user_id)
        
        # Validar si tenemos credenciales antes de intentar operar
        if not getattr(exchange, 'apiKey', None):
             return {"success": False, "message": f"No API Credentials found for {exchange_id}"}

        try:
            side_low = side.lower()
            if not price:
                order = await exchange.create_market_order(symbol, side_low, amount)
            else:
                order = await exchange.create_limit_order(symbol, side_low, amount, price)
            
            return {"success": True, "order_id": order.get('id'), "status": order.get('status'), "details": order}
        except Exception as e:
            logger.error(f"Error executing trade on {exchange_id}: {e}")
            return {"success": False, "message": str(e)}

    async def get_historical_data(self, symbol: str, timeframe: str, limit: int = 100, user_id: str = None, exchange_id: str = 'binance', use_random_date: bool = False, **kwargs) -> pd.DataFrame:
        """
        Obtiene datos históricos (velas).
        Si use_random_date = True, busca un punto aleatorio en el tiempo (para entrenamiento ML).
        """
        exchange = await self._get_exchange(exchange_id, user_id)
        
        since = None
        if use_random_date:
            import random
            from datetime import timedelta
            # Elegir un punto aleatorio en los últimos 2 años
            days_back = random.randint(30, 730)
            start_date = datetime.utcnow() - timedelta(days=days_back)
            since = int(start_date.timestamp() * 1000)

        try:
            ohlcv = await exchange.fetch_ohlcv(symbol, timeframe, limit=limit, since=since)
            if not ohlcv:
                return pd.DataFrame()
                
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('timestamp', inplace=True)
            return df
        except Exception as e:
            logger.error(f"Error fetching historical data for {symbol}: {e}")
            return pd.DataFrame()

    async def get_public_current_price(self, symbol: str, exchange_id: str = 'binance') -> float:
        """Obtiene el precio actual rápido vía REST."""
        exchange = await self._get_exchange(exchange_id)
        try:
            ticker = await exchange.fetch_ticker(symbol)
            return float(ticker['last'])
        except Exception as e:
            logger.error(f"Error fetching public price for {symbol} on {exchange_id}: {e}")
            return 0.0

    async def fetch_balance(self, user_id: str, exchange_id: str = 'okx') -> List[Any]:
        exchange = await self._get_exchange(exchange_id, user_id)
        
        if not getattr(exchange, 'apiKey', None):
            logger.warning(f"Attempted fetch_balance on {exchange_id} without API Key for user {user_id}")
            return []

        try:
            balance_data = await exchange.fetch_balance()
            from api.src.domain.entities.trading import Balance
            balances = []
            if 'total' in balance_data:
                for asset, total in balance_data['total'].items():
                    if total > 0:
                        balances.append(Balance(
                            asset=asset, 
                            free=balance_data['free'].get(asset, 0.0),
                            used=balance_data['used'].get(asset, 0.0),
                            total=total
                        ))
            return balances
        except Exception as e:
            logger.error(f"Error fetching balance for {user_id} on {exchange_id}: {e}")
            return []

    async def fetch_open_orders(self, symbol: Optional[str] = None, user_id: str = None, exchange_id: str = 'binance') -> List[Dict[str, Any]]:
        exchange = await self._get_exchange(exchange_id, user_id)
        try:
            return await exchange.fetch_open_orders(symbol)
        except Exception as e:
            logger.error(f"Error fetching open orders on {exchange_id}: {e}")
            return []

    async def close_all(self):
        for exchange in self.exchanges.values():
            await exchange.close()
        logger.info("Conexiones CCXT Pro cerradas.")

# Exportar para compatibilidad
ccxt_service = CcxtAdapter()