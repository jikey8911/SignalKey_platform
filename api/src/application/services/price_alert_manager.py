import asyncio
import logging

logger = logging.getLogger(__name__)

class PriceAlertManager:
    def __init__(self, stream_service):
        self.stream_service = stream_service
        self.active_alerts = {} # { "symbol": [Future, target_price] }

    async def wait_for_proximity(self, exchange_id: str, symbol: str, target_price: float, threshold=0.005):
        """
        Mantiene la tarea en suspenso hasta que el precio esté a < 0.5% (threshold)
        """
        logger.info(f"📡 Vigilante pasivo iniciado: {symbol} objetivo {target_price}")
        
        try:
            while True:
                # Usamos el stream más ligero: Ticker
                # Nota: El servicio debe devolver el último dato conocido
                ticker = await self.stream_service.subscribe_ticker(exchange_id, symbol)
                
                current_price = ticker.get('last', 0)
                if current_price > 0:
                    distancia = abs(current_price - target_price) / target_price
                    
                    if distancia <= threshold:
                        logger.info(f"🎯 ZONA DE INTERÉS: {symbol} alcanzó {current_price}. Despertando bot...")
                        return current_price
                
                # Pequeña pausa para no saturar el event loop si el stream es muy rápido
                await asyncio.sleep(0.5) # Aumentado un poco para mayor ahorro de CPU en fase pasiva
        except Exception as e:
            logger.error(f"Error en vigilante de {symbol}: {e}")
            raise
