import ccxt.async_support as ccxt
import logging
import aiohttp
from aiohttp.resolver import ThreadedResolver
from typing import Optional, Dict, Any, Tuple

logger = logging.getLogger(__name__)

class CCXTService:
    def __init__(self):
        self.public_instances = {}

    def _create_custom_session(self):
        """Creates an aiohttp session with ThreadedResolver to bypass Windows Async DNS issues"""
        try:
            resolver = ThreadedResolver()
            connector = aiohttp.TCPConnector(resolver=resolver)
            return aiohttp.ClientSession(connector=connector)
        except Exception as e:
            logger.error(f"Error creating custom session: {e}")
            return None

    async def create_public_instance(self, exchange_id: str):
        exchange_id = exchange_id.lower()
        if exchange_id in self.public_instances:
            return self.public_instances[exchange_id]

        try:
            exchange_class = getattr(ccxt, exchange_id)
            instance = exchange_class({
                'enableRateLimit': True,
                'options': {
                    'defaultType': 'spot',
                    'fetchCurrencies': False
                }
            })
            
            # Inject custom session for Windows DNS fix
            session = self._create_custom_session()
            if session:
                instance.session = session

            if exchange_id == 'okx':
                instance.has['fetchCurrencies'] = False
            self.public_instances[exchange_id] = instance
            return instance
        except Exception as e:
            logger.error(f"Error al crear instancia pública {exchange_id}: {e}")
            return None

    async def get_private_instance(self, exchange_id: str, api_key: str, secret: str, password: str = None, uid: str = None):
        """
        Crea y retorna una instancia privada lista para usar.
        Nota: Debe ser cerrada después de su uso con await instance.close()
        """
        exchange_id = exchange_id.lower()
        try:
            exchange_class = getattr(ccxt, exchange_id)
            config = {
                'apiKey': api_key,
                'secret': secret,
                'enableRateLimit': True,
                'options': {
                    'defaultType': 'spot',
                    'fetchCurrencies': False,
                    'warnOnNoBalance': False
                }
            }
            
            # Ajustes específicos para OKX para evitar asset/currencies
            if exchange_id == 'okx':
                config['options']['fetchBalance'] = {'type': 'trading'}
                # Algunos versiones de ccxt usan estas llaves para evitar el endpoint de assets
                config['has'] = {
                    'fetchCurrencies': False,
                    'fetchBalance': True
                }
                
            if password: config['password'] = password
            if uid: config['uid'] = uid
            
            instance = exchange_class(config)
            
            # Inject custom session for Windows DNS fix
            session = self._create_custom_session()
            if session:
                instance.session = session
            
            # Forzar desactivación de fetchCurrencies en el objeto 'has' para OKX
            if exchange_id == 'okx':
                instance.has['fetchCurrencies'] = False
                
            return instance
        except Exception as e:
            logger.error(f"Error al configurar instancia privada {exchange_id}: {e}")
            return None

    async def test_connection_private(self, exchange_id: str, api_key: str, secret: str, password: str = None, uid: str = None) -> Tuple[bool, str]:
        """Prueba la conexión obteniendo el balance."""
        instance = await self.get_private_instance(exchange_id, api_key, secret, password, uid)
        if not instance:
            return False, f"Exchange '{exchange_id}' no soportado o mal configurado"

        try:
            # 1. Intentar cargar mercados (prueba conectividad básica y carga de símbolos)
            try:
                await instance.load_markets()
            except Exception as e:
                # Si falla load_markets, puede ser por network error en currencies
                logger.debug(f"CCXTService: load_markets falló (posible asset/currencies error), continuando: {e}")
            
            # 2. Prueba autenticada real
            params = {}
            if exchange_id.lower() == 'okx':
                params['type'] = 'spot' # O 'trading'
            
            try:
                await instance.fetch_balance(params=params)
                return True, "Conexión exitosa"
            except (ccxt.NetworkError, ccxt.ExchangeError) as e:
                # Si falla balance por permisos de asset, intentamos una acción mínima autenticada
                # fetch_open_orders es excelente para probar llaves de 'Trade' sin requerir 'Asset'
                logger.debug(f"CCXTService: fetch_balance falló para {exchange_id}, reintentando con validación mínima: {e}")
                try:
                    # En algunos exchanges instType es necesario o se asume por defaultType
                    await instance.fetch_open_orders(params=params)
                    return True, "Conexión exitosa (Validada vía órdenes)"
                except Exception as final_e:
                    logger.error(f"CCXTService: Todas las validaciones fallaron para {exchange_id}: {final_e}")
                    # Si llegamos aquí con un error de red específico de currencies, devolvemos un mensaje descriptivo
                    msg = str(final_e)
                    if "asset/currencies" in msg:
                        return False, "Error de OKX: Las API Keys no tienen permisos de lectura de activos. Active permisos de 'Trading' y 'Reading'."
                    return False, msg
            
        except ccxt.AuthenticationError:
            return False, "Error de autenticación: API Key o Secret inválidos"
        except ccxt.PermissionDenied:
            return False, "Permisos insuficientes: La API Key no tiene permisos de lectura/balance"
        except Exception as e:
            logger.error(f"Error en test_connection para {exchange_id}: {str(e)}")
            return False, f"Error de conexión: {str(e)}"
        finally:
            # ES CRÍTICO cerrar la conexión en async
            await instance.close()

    async def fetch_balance_private(self, exchange_id: str, api_key: str, secret: str, password: str = None, uid: str = None) -> Dict:
        """Obtiene el balance total."""
        instance = await self.get_private_instance(exchange_id, api_key, secret, password, uid)
        if not instance:
            return {}

        try:
            params = {}
            if exchange_id.lower() == 'okx':
                params['type'] = 'spot'
            
            balance = await instance.fetch_balance(params=params)
            return balance
        except Exception as e:
            logger.error(f"Error al obtener balance de {exchange_id}: {e}")
            return {}
        finally:
            await instance.close()

    async def close_all(self):
        """Cierra todas las instancias públicas"""
        for instance in self.public_instances.values():
            try:
                await instance.close()
            except:
                pass
        self.public_instances = {}

    async def get_markets(self, exchange_id: str) -> list:
        """
        Obtiene los tipos de mercado disponibles para un exchange
        
        Args:
            exchange_id: ID del exchange
            
        Returns:
            Lista de tipos de mercado únicos (spot, future, swap, etc.)
        """
        try:
            instance = await self.create_public_instance(exchange_id)
            if not instance:
                return []
            
            await instance.load_markets()
            
            # Extraer tipos de mercado únicos
            market_types = set()
            for market_id, market in instance.markets.items():
                market_type = market.get('type', 'spot')
                market_types.add(market_type)
            
            return sorted(list(market_types))
            
        except Exception as e:
            logger.error(f"Error fetching markets for {exchange_id}: {e}")
            return []

    async def get_symbols_with_tickers(self, exchange_id: str, market_type: str = 'spot') -> list:
        """
        Obtiene símbolos con datos de precio y cambio porcentual
        
        Args:
            exchange_id: ID del exchange
            market_type: Tipo de mercado (spot, future, swap, etc.)
            
        Returns:
            Lista de diccionarios con symbol, price, priceChange, priceChangePercent
        """
        try:
            instance = await self.create_public_instance(exchange_id)
            if not instance:
                return []
            
            await instance.load_markets()
            
            # Filtrar símbolos por tipo de mercado
            filtered_symbols = []
            for symbol, market in instance.markets.items():
                if market.get('type', 'spot') == market_type and market.get('active', True):
                    filtered_symbols.append(symbol)
            
            # Limitar a 100 símbolos para evitar sobrecarga
            filtered_symbols = filtered_symbols[:100]
            
            # Obtener tickers
            try:
                tickers = await instance.fetch_tickers(filtered_symbols)
            except Exception as e:
                logger.warning(f"Error fetching tickers for {exchange_id}, trying individual fetch: {e}")
                # Si falla fetch_tickers, intentar uno por uno (más lento pero más confiable)
                tickers = {}
                for symbol in filtered_symbols[:20]:  # Limitar aún más si es individual
                    try:
                        ticker = await instance.fetch_ticker(symbol)
                        tickers[symbol] = ticker
                    except:
                        continue
            
            # Formatear respuesta
            result = []
            for symbol, ticker in tickers.items():
                market = instance.markets.get(symbol, {})
                result.append({
                    'symbol': symbol,
                    'baseAsset': market.get('base', ''),
                    'quoteAsset': market.get('quote', ''),
                    'price': ticker.get('last', 0),
                    'priceChange': ticker.get('change', 0),
                    'priceChangePercent': ticker.get('percentage', 0),
                    'volume': ticker.get('quoteVolume', 0)
                })
            
            # Ordenar por volumen descendente
            result.sort(key=lambda x: x['volume'], reverse=True)
            
            return result
            
        except Exception as e:
            logger.error(f"Error fetching symbols with tickers for {exchange_id}: {e}")
            return []

ccxt_service = CCXTService()
