import asyncio
import logging
from datetime import datetime
from bson import ObjectId
from api.src.adapters.driven.persistence.mongodb_bot_repository import MongoBotRepository
from api.src.application.services.execution_engine import ExecutionEngine
from api.src.adapters.driven.persistence.mongodb import db as db_adapter # Asumimos db global disponible
from api.src.adapters.driven.exchange.ccxt_adapter import ccxt_service

logger = logging.getLogger("BootManager")

class BootManager:
    """
    Servicio de Resiliencia (Tarea 7.2).
    Se asegura de que los bots 'active' reanuden su monitoreo tras un reinicio de la API.
    """
    def __init__(self, db_adapter_in=None, socket_service=None, exchange_adapter=None):
        self.repo = MongoBotRepository()
        # Usamos el db_adapter pasado o el global si no se pasa (para compatibilidad)
        final_db = db_adapter_in if db_adapter_in is not None else db_adapter
        final_exchange = exchange_adapter if exchange_adapter else ccxt_service
        self.socket_service = socket_service
        self.engine = ExecutionEngine(final_db, socket_service, exchange_adapter=final_exchange)

    async def initialize_active_bots(self):
        """
        Busca en MongoDB y relanza los procesos de monitoreo.
        """
        logger.info("Iniciando proceso de recuperación de bots...")
        
        # 1. Iniciar el streaming de precios centralizado (NUEVO)
        asyncio.create_task(self._price_streaming_loop())
        
        try:
            # get_active_bots devuelve objetos BotInstance
            active_bots = await self.repo.get_active_bots()
            
            if not active_bots:
                logger.info("No se encontraron bots activos para recuperar (status='active' en bot_instances).")
                return

            count = 0
            for bot_entity in active_bots:
                # Convertimos entidad a dict para el motor o lógica subsiguiente
                bot_data = bot_entity.to_dict()
                logger.info(f"Reactivando bot: {bot_data.get('name')} ({bot_data.get('symbol')}) - User: {bot_data.get('user_id')}")
                
                # Lanzar ciclo de monitoreo en background
                asyncio.create_task(self.monitor_loop(bot_data))
                count += 1
                
            logger.info(f"✅ Se han reanudado {count} instancias exitosamente.")
            
        except Exception as e:
            logger.error(f"Fallo crítico en la recuperación automática: {e}")

    async def _price_streaming_loop(self):
        """Bucle centralizado que emite precios actuales para todos los bots activos."""
        logger.info("📡 Iniciando Streaming de Precios Live...")
        while True:
            try:
                if not self.socket_service:
                    await asyncio.sleep(5)
                    continue

                active_bots = await self.repo.get_active_bots()
                if not active_bots:
                    await asyncio.sleep(10)
                    continue

                # Agrupar por (símbolo, exchange) para optimizar llamadas a la API
                # Llave: (symbol, exchange_id)
                group_map = {}
                for bot in active_bots:
                    sym = bot.symbol
                    ex_id = getattr(bot, 'exchange_id', None) or getattr(bot, 'exchangeId', 'binance')
                    key = (sym, ex_id)
                    if key not in group_map:
                        group_map[key] = []
                    group_map[key].append(bot)

                for (symbol, exchange_id), bots in group_map.items():
                    try:
                        # Obtenemos precio público usando el exchange correcto
                        price = await ccxt_service.get_public_current_price(symbol, exchange_id=exchange_id)
                        
                        # Notificar a cada usuario del bot
                        for bot in bots:
                            user_id = str(bot.user_id)
                            await self.socket_service.emit_to_user(user_id, "price_update", {
                                "bot_id": str(bot.id),
                                "symbol": symbol,
                                "price": price,
                                "exchange_id": exchange_id,
                                "timestamp": datetime.utcnow().isoformat()
                            })
                    except Exception as e:
                        # Error de mercado o símbolo no encontrado - Logueamos una sola vez o con nivel info si es común
                        if "does not have market symbol" in str(e).lower() or "symbol not found" in str(e).lower():
                            logger.warning(f"⚠️ Símbolo {symbol} no disponible en el exchange {exchange_id}. Saltando...")
                        else:
                            logger.error(f"Error streaming price for {symbol} on {exchange_id}: {e}")

            except Exception as e:
                logger.error(f"Error crítico en _price_streaming_loop: {e}")
            
            await asyncio.sleep(5) # Actualización cada 5 segundos

    async def monitor_loop(self, bot_data):
        """
        Bucle de monitoreo autónomo (Autotrading).
        Realiza análisis técnico periódico y ejecuta señales vía IA.
        """
        bot_id = bot_data.get('id')
        symbol = bot_data.get('symbol')
        timeframe = bot_data.get('timeframe', '1h')
        market_type = bot_data.get('market_type', 'spot')
        user_id = bot_data.get('user_id')
        
        # --- FIX: Extraer el Exchange ID del bot ---
        # Intentamos ambas nomenclaturas por seguridad
        exchange_id = bot_data.get('exchange_id') or bot_data.get('exchangeId')
        
        logger.info(f"🟢 Bucle Autotrade iniciado para {bot_id} ({symbol} | {timeframe}) en Exchange: {exchange_id}")

        from api.src.application.services.ml_service import MLService
        from api.src.adapters.driven.exchange.ccxt_adapter import ccxt_service
        ml_service = MLService(ccxt_service)

        try:
            while True:
                # 1. Verificar si el autotrading sigue activo para el usuario
                from api.src.adapters.driven.persistence.mongodb import get_app_config
                config = await get_app_config(user_id)

                # Default behavior: If config is None (DB error/User not found), we assume autotrade is ENABLED
                is_auto_enabled = True
                if config:
                    is_auto_enabled = config.get('isAutoEnabled', True)
                else:
                    logger.warning(f"⚠️ No se pudo obtener config para usuario {user_id}. Asumiendo isAutoEnabled=True para bot {bot_id}.")

                if not is_auto_enabled:
                    logger.info(f"⏸️ Autotrade desactivado globalmente para usuario {user_id}. Bot {bot_id} pausado.")
                    break
                
                # 2. Obtener datos recientes
                try:
                    # --- FIX: Pasar exchange_id y user_id explícitamente ---
                    # Esto fuerza al adaptador a usar las credenciales y mercado correctos (ej: OKX) en lugar de default (Binance)
                    candles_df = await ccxt_service.get_historical_data(
                        symbol, 
                        timeframe, 
                        limit=100,
                        user_id=str(user_id), # Aseguramos string
                        exchange_id=exchange_id
                    )
                    
                    if not candles_df.empty:
                        candles_list = []
                        for ts, row in candles_df.iterrows():
                            candles_list.append({
                                "time": ts.timestamp(),
                                "open": row['open'], "high": row['high'],
                                "low": row['low'], "close": row['close']
                            })

                        # 3. Predecir señal
                        current_bot = await self.repo.collection.find_one({"_id": ObjectId(bot_id)})
                        prediction = ml_service.predict(
                            symbol=symbol,
                            timeframe=timeframe,
                            candles=candles_list,
                            market_type=market_type,
                            strategy_name=bot_data.get('strategy_name'),
                            current_position=current_bot.get('position')
                        )

                        decision = prediction.get('decision')
                        if decision in ["BUY", "SELL"]:
                            logger.info(f"🤖 IA decidió {decision} para {symbol}")
                            signal_val = 1 if decision == "BUY" else 2

                            # 4. Procesar señal a través del motor
                            await self.engine.process_signal(current_bot, {
                                "signal": signal_val,
                                "price": candles_list[-1]['close'],
                                "confidence": prediction.get('confidence'),
                                "reasoning": prediction.get('reasoning') or f"Strategy: {bot_data.get('strategy_name')}",
                                "is_alert": False 
                            })

                except Exception as e:
                    logger.error(f"⚠️ Error analizando mercado para bot {bot_id} en {exchange_id}: {e}")

                # Esperar al siguiente intervalo (ej: 1 minuto)
                await asyncio.sleep(60)
                
        except asyncio.CancelledError:
            logger.info(f"🔴 Bucle Autotrade cancelado para {bot_id}")
        except Exception as e:
            logger.error(f"Error crítico en bucle Autotrade {bot_id}: {e}")

