import asyncio
import logging
import ccxt.pro as ccxtpro
from typing import Dict, Any, Optional, AsyncGenerator, List
import pandas as pd
from datetime import datetime

logger = logging.getLogger("CCXTAdapter")

class CCXTService:
    """
    Adaptador para CCXT Pro.
    Implementa WebSockets para datos en tiempo real y métodos REST para ejecución.
    """
    def __init__(self, **kwargs):
        self.exchanges: Dict[str, ccxtpro.Exchange] = {}
        self._locks: Dict[str, asyncio.Lock] = {}
        self.db = kwargs.get('db_adapter') # Guardamos si se provee

    async def _get_exchange(self, exchange_id: str, user_id: str = None) -> ccxtpro.Exchange:
        """
        Obtiene o crea una instancia de exchange Pro.
        TODO: En el futuro, cargar las credenciales del user_id desde la DB.
        """
        eid = exchange_id.lower()
        # Clave única por exchange (y usuario si tuviera credenciales distintas)
        instance_key = f"{eid}:{user_id}" if user_id else eid
        
        if instance_key not in self._locks:
            self._locks[instance_key] = asyncio.Lock()
            
        async with self._locks[instance_key]:
            if instance_key not in self.exchanges:
                exchange_class = getattr(ccxtpro, eid)
                self.exchanges[instance_key] = exchange_class({
                    'enableRateLimit': True,
                    'options': {
                        'defaultType': 'spot',
                        'fetchCurrencies': False
                    }
                })
            return self.exchanges[instance_key]

    # --- MÉTODOS DE STREAMING (WEBSOCKETS) ---

    async def watch_ticker(self, exchange_id: str, symbol: str) -> AsyncGenerator[Dict[str, Any], None]:
        """Generador asíncrono para Tickers en tiempo real."""
        exchange = await self._get_exchange(exchange_id)
        while True:
            try:
                ticker = await exchange.watch_ticker(symbol)
                yield ticker
            except Exception as e:
                logger.error(f"Error en watch_ticker ({exchange_id}:{symbol}): {e}")
                await asyncio.sleep(5)

    async def watch_ohlcv(self, exchange_id: str, symbol: str, timeframe: str) -> AsyncGenerator[list, None]:
        """Generador asíncrono para Velas (OHLCV) en tiempo real."""
        exchange = await self._get_exchange(exchange_id)
        while True:
            try:
                ohlcv = await exchange.watch_ohlcv(symbol, timeframe)
                if ohlcv:
                    yield ohlcv
            except Exception as e:
                logger.error(f"Error en watch_ohlcv ({exchange_id}:{symbol}:{timeframe}): {e}")
                await asyncio.sleep(5)

    # --- MÉTODOS DE DATOS HISTÓRICOS (REST) ---

    async def get_historical_data(self, symbol: str, timeframe: str, limit: int = 100, user_id: str = None, exchange_id: str = 'okx') -> pd.DataFrame:
        """Obtiene velas históricas vía REST para inicializar buffers o análisis."""
        exchange = await self._get_exchange(exchange_id, user_id)
        try:
            ohlcv = await exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('timestamp', inplace=True)
            return df
        except Exception as e:
            logger.error(f"Error fetching historical data: {e}")
            return pd.DataFrame()

    async def get_public_current_price(self, symbol: str, exchange_id: str = 'okx') -> float:
        """Obtiene el precio actual rápido vía REST."""
        exchange = await self._get_exchange(exchange_id)
        try:
            ticker = await exchange.fetch_ticker(symbol)
            return float(ticker['last'])
        except Exception as e:
            logger.error(f"Error fetching public price for {symbol}: {e}")
            return 0.0

    # --- MÉTODOS DE EJECUCIÓN (REQUERIDOS POR CEXService) ---

    async def execute_trade(self, symbol: str, side: str, amount: float, price: Optional[float] = None, user_id: str = None, exchange_id: str = 'okx') -> Dict[str, Any]:
        """Ejecuta una orden en el exchange."""
        exchange = await self._get_exchange(exchange_id, user_id)
        try:
            order_type = 'limit' if price else 'market'
            if order_type == 'market':
                order = await exchange.create_market_order(symbol, side.lower(), amount)
            else:
                order = await exchange.create_limit_order(symbol, side.lower(), amount, price)
            
            return {
                "success": True,
                "order_id": order.get('id'),
                "status": order.get('status'),
                "details": order
            }
        except Exception as e:
            logger.error(f"Error executing trade on {exchange_id}: {e}")
            return {"success": False, "message": str(e)}

    async def fetch_open_orders(self, symbol: Optional[str] = None, user_id: str = None, exchange_id: str = 'okx') -> List[Dict[str, Any]]:
        """Consulta órdenes abiertas."""
        exchange = await self._get_exchange(exchange_id, user_id)
        try:
            return await exchange.fetch_open_orders(symbol)
        except Exception as e:
            logger.error(f"Error fetching open orders on {exchange_id}: {e}")
            return []

    async def fetch_balance(self, user_id: str, exchange_id: str = 'okx') -> List[Any]:
        """Consulta el balance del usuario."""
        exchange = await self._get_exchange(exchange_id, user_id)
        try:
            balance_data = await exchange.fetch_balance()
            from api.src.domain.entities.trading import Balance
            balances = []
            if 'total' in balance_data:
                for asset, total in balance_data['total'].items():
                    if total > 0:
                        free = balance_data['free'].get(asset, 0.0)
                        used = balance_data['used'].get(asset, 0.0)
                        balances.append(Balance(asset=asset, free=free, used=used, total=total))
            return balances
        except Exception as e:
            logger.error(f"Error fetching balance for {user_id} on {exchange_id}: {e}")
            return []

    async def get_markets(self, exchange_id: str) -> List[str]:
        """Carga y retorna los tipos de mercado disponibles."""
        exchange = await self._get_exchange(exchange_id)
        try:
            await exchange.load_markets()
            market_types = {market.get('type') for market in exchange.markets.values() if market.get('type')}
            return sorted(list(market_types))
        except Exception as e:
            logger.error(f"Error fetching markets for {exchange_id}: {e}")
            return []

    async def get_symbols(self, exchange_id: str, market_type: str) -> List[str]:
        """Retorna los símbolos disponibles para un tipo de mercado."""
        exchange = await self._get_exchange(exchange_id)
        try:
            await exchange.load_markets()
            symbols = [s for s, m in exchange.markets.items() if m.get('type') == market_type and m.get('active', True)]
            return sorted(symbols)
        except Exception as e:
            logger.error(f"Error fetching symbols for {exchange_id} ({market_type}): {e}")
            return []

    async def get_public_historical_data(self, symbol: str, timeframe: str, limit: int = 1500, use_random_date: bool = False, exchange_id: str = "okx") -> pd.DataFrame:
        """Alias para compatibilidad con Backtest y MLService."""
        return await self.get_historical_data(symbol, timeframe, limit=limit, use_random_date=use_random_date, exchange_id=exchange_id)

    async def close_all(self):
        """Cierra todas las conexiones activas."""
        for exchange in self.exchanges.values():
            await exchange.close()
        logger.info("Todas las conexiones de CCXT Pro han sido cerradas.")

# Instancia global para ser importada por otros servicios
CcxtAdapter = CCXTService
ccxt_service = CCXTService()