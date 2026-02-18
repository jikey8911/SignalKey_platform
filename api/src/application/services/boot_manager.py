import asyncio
import logging
from datetime import datetime
from api.src.adapters.driven.persistence.mongodb_bot_repository import MongoBotRepository
from api.src.application.services.execution_engine import ExecutionEngine
from api.src.adapters.driven.persistence.mongodb import db as db_global
from api.src.adapters.driven.exchange.ccxt_adapter import ccxt_service

logger = logging.getLogger("BootManager")

class BootManager:
    """
    Servicio de Resiliencia.
    Ahora utiliza suscripciones dinámicas a través de StreamService.
    """
    def __init__(self, db_adapter_in=None, socket_service=None, stream_service=None):
        self.repo = MongoBotRepository()
        self.socket_service = socket_service
        self.stream_service = stream_service # Inyectado desde el arranque global
        self.engine = ExecutionEngine(
            db_adapter_in if db_adapter_in is not None else db_global, 
            socket_service, 
            exchange_adapter=ccxt_service
        )

    async def initialize_active_bots(self):
        """Relanza el monitoreo para bots activos usando flujos de eventos."""
        logger.info("Iniciando recuperación de bots (Modo Event-Driven)...")
        
        try:
            active_bots = await self.repo.get_active_bots()
            if not active_bots:
                logger.info("No hay bots activos para recuperar.")
                return

            for bot_entity in active_bots:
                bot_data = bot_entity.to_dict()
                symbol = bot_data.get('symbol')
                exchange_id = (bot_data.get('exchange_id') or bot_data.get('exchangeId') or 'okx').lower()
                timeframe = bot_data.get('timeframe', '15m')
                market_type = str(bot_data.get('market_type') or bot_data.get('marketType') or 'spot').lower()
                user_id = str(bot_data.get('user_id'))

                logger.info(f"Reactivando streams para {bot_data['name']} en {exchange_id}")

                # 1. Suscribir a precio real para el frontend
                if self.stream_service:
                    await self.stream_service.subscribe_ticker(exchange_id, symbol, market_type=market_type)

                    # 2. Suscribir a velas para la lógica de la IA
                    await self.stream_service.subscribe_candles(exchange_id, symbol, timeframe, market_type=market_type)
                
                # 3. Lanzar bucle de monitoreo (que ahora responderá a eventos del stream_service)
                # El monitor_loop ahora puede ser más ligero ya que el stream_service hace el trabajo pesado
                asyncio.create_task(self.monitor_loop_v3(bot_data))
            
            logger.info(f"✅ Recuperación completada para {len(active_bots)} bots.")
            
        except Exception as e:
            logger.error(f"Fallo en BootManager: {e}", exc_info=True)

    async def monitor_loop_v3(self, bot_data):
        """
        Bucle ligero que mantiene viva la lógica del bot. 
        En esta arquitectura, la mayor parte del trabajo se delega al 
        handler de eventos de SignalBotService.
        """
        bot_id = bot_data.get('id')
        logger.info(f"🟢 Monitor V3 activo para Bot {bot_id}")
        
        try:
            while True:
                # Simplemente dormimos; la lógica real se dispara en 
                # SignalBotService._handle_candle_update vía eventos
                await asyncio.sleep(3600) 
        except asyncio.CancelledError:
            logger.info(f"🔴 Monitor cancelado para {bot_id}")
