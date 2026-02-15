import asyncio
import logging

logger = logging.getLogger(__name__)

class PriceAlertManager:
    def __init__(self, stream_service):
        self.stream_service = stream_service
        self.active_alerts = {}  # { "key": Future }

    async def wait_for_proximity(
        self,
        exchange_id: str,
        symbol: str,
        target_price: float,
        market_type: str = None,
        threshold: float = 0.005,
        threshold_percent: float = None,
    ):
        """Espera pasiva hasta que el precio esté lo suficientemente cerca del target.

        - `threshold`: fracción (0.005 = 0.5%)
        - `threshold_percent`: porcentaje (0.5 = 0.5%)

        Se acepta `threshold_percent` para compatibilidad con el flujo Sueño/Vigilia.
        """
        if threshold_percent is not None:
            threshold = float(threshold_percent) / 100.0

        logger.info(f"📡 Vigilante pasivo iniciado: {symbol} objetivo {target_price} (±{threshold*100:.3f}%)")
        
        try:
            while True:
                # Usamos el stream más ligero: Ticker
                # Nota: El servicio debe devolver el último dato conocido
                ticker = await self.stream_service.subscribe_ticker(exchange_id, symbol, market_type=market_type)
                
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
