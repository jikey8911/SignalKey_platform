import asyncio
import logging
from bson import ObjectId
from api.src.adapters.driven.persistence.mongodb_bot_repository import MongoBotRepository
from api.src.application.services.execution_engine import ExecutionEngine
from api.src.adapters.driven.persistence.mongodb import db as db_adapter # Asumimos db global disponible

logger = logging.getLogger("BootManager")

class BootManager:
    """
    Servicio de Resiliencia (Tarea 7.2).
    Se asegura de que los bots 'active' reanuden su monitoreo tras un reinicio de la API.
    """
    def __init__(self, db_adapter_in=None, socket_service=None):
        self.repo = MongoBotRepository()
        # Usamos el db_adapter pasado o el global si no se pasa (para compatibilidad)
        final_db = db_adapter_in if db_adapter_in is not None else db_adapter
        self.engine = ExecutionEngine(final_db, socket_service)

    async def initialize_active_bots(self):
        """
        Busca en MongoDB y relanza los procesos de monitoreo.
        """
        logger.info("Iniciando proceso de recuperación de bots...")
        
        try:
            # get_active_bots devuelve objetos BotInstance
            active_bots = await self.repo.get_active_bots()
            
            if not active_bots:
                logger.info("No se encontraron bots activos para recuperar.")
                return

            count = 0
            for bot_entity in active_bots:
                # Convertimos entidad a dict para el motor o lógica subsiguiente
                bot_data = bot_entity.to_dict()
                logger.info(f"Reactivando bot: {bot_data.get('name')} ({bot_data.get('symbol')})")
                
                # Lanzar ciclo de monitoreo en background
                asyncio.create_task(self.monitor_loop(bot_data))
                count += 1
                
            logger.info(f"Se han reanudado {count} instancias exitosamente.")
            
        except Exception as e:
            logger.error(f"Fallo crítico en la recuperación automática: {e}")

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
        
        logger.info(f"🟢 Bucle Autotrade iniciado para {bot_id} ({symbol} | {timeframe})")

        from api.src.application.services.ml_service import MLService
        from api.src.adapters.driven.exchange.ccxt_adapter import ccxt_service
        ml_service = MLService(ccxt_service)

        try:
            while True:
                # 1. Verificar si el autotrading sigue activo para el usuario
                from api.src.adapters.driven.persistence.mongodb import get_app_config
                config = await get_app_config(user_id)
                if not config or not config.get('isAutoEnabled', True):
                    logger.info(f"⏸️ Autotrade desactivado globalmente para usuario {user_id}. Bot {bot_id} pausado.")
                    break
                
                # 2. Obtener datos recientes
                try:
                    # Obtenemos las últimas 100 velas
                    candles_df = await ccxt_service.get_historical_data(symbol, timeframe, limit=100)
                    if not candles_df.empty:
                        candles_list = []
                        for ts, row in candles_df.iterrows():
                            candles_list.append({
                                "time": ts.timestamp(),
                                "open": row['open'], "high": row['high'],
                                "low": row['low'], "close": row['close']
                            })

                        # 3. Predecir señal
                        # S9: Pasar posición actual para contexto
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
                                "is_alert": False # Permitir Profit Guard normal
                            })

                except Exception as e:
                    logger.error(f"⚠️ Error analizando mercado para bot {bot_id}: {e}")

                # Esperar al siguiente intervalo (ej: 1 minuto)
                await asyncio.sleep(60)
                
        except asyncio.CancelledError:
            logger.info(f"🔴 Bucle Autotrade cancelado para {bot_id}")
        except Exception as e:
            logger.error(f"Error crítico en bucle Autotrade {bot_id}: {e}")
