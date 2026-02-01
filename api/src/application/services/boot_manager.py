import asyncio
import logging
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
        final_db = db_adapter_in if db_adapter_in else db_adapter
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
        Bucle de monitoreo persistente para cada bot recuperado.
        SIMULACIÓN: En producción real, esto conectaría con WebSockets o polling de precios.
        """
        bot_id = bot_data.get('id')
        logger.info(f"🟢 Monitor loop started for {bot_id}")
        
        try:
            while True:
                # Verificar si sigue activo en DB (Heartbeat)
                # En una implementación real, aquí procesaríamos señales o precios
                # Por ahora, mantenemos vivo el proceso y logueamos ocasionalmente
                await asyncio.sleep(60) # Revisar cada minuto
                
                # Opcional: Validar si el usuario lo detuvo externamente
                # current_status = await self.repo.get_status(bot_id)
                # if current_status != 'active': break
                
        except asyncio.CancelledError:
            logger.info(f"🔴 Monitor loop cancelled for {bot_id}")
        except Exception as e:
            logger.error(f"Error in monitor loop for {bot_id}: {e}")
