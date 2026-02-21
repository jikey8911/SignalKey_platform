"""
Script de re-entrenamiento masivo para estrategias v2.0

Uso:
    python scripts/retrain_models.py
"""
import asyncio
import logging
import sys
import os

# Agregar ruta raíz al path de forma robusta
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir) # SignaalKei_platform
sys.path.append(project_root)

# También agregar 'api' si fuera necesario, pero con project_root debería bastar si los imports son "api.src..."
api_root = os.path.join(project_root, 'api')
sys.path.append(api_root)

from api.src.application.services.ml_service import MLService
from api.src.application.services.cex_service import CEXService
from api.src.domain.services.strategy_trainer import StrategyTrainer

# Configurar logs
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("RetrainScript")

async def main():
    logger.info("🚀 Iniciando re-entrenamiento de modelos v2.0...")
    
    try:
        # 1. Inicializar servicios
        # Usamos CEXService dummy (sin API keys)
        ml_service = MLService(exchange_adapter=CEXService())
        trainer = StrategyTrainer()
        
        # 2. Descubrir estrategias SPOT
        strategies = trainer.discover_strategies(market_type="spot")
        logger.info(f"🔍 Estrategias encontradas: {len(strategies)}")
        logger.info(f"📋 Lista: {strategies}")
        
        if not strategies:
            logger.error("❌ No se encontraron estrategias. Revisa la ruta api/src/domain/strategies/spot/")
            return

        # 3. Configuración de entrenamiento
        # Entrenamos con los principales pares para tener un modelo generalista robusto
        symbols = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT", "BNB/USDT"]
        timeframe = "1h"
        days = 180 # 6 meses para ser más rápido en prueba, ajustar a 365 para prod
        market_type = "spot"
        user_id = "system_retrain"
        
        logger.info(f"⚙️ Config: {len(symbols)} símbolos, TF={timeframe}, Días={days}")
        
        # 4. Ejecutar entrenamiento
        logger.info(f"🏋️ Entrenando modelos...")
        
        # MLService.train_all_strategies entrena UN modelo por estrategia (usando todos los símbolos)
        await ml_service.train_all_strategies(
            symbols=symbols,
            timeframe=timeframe,
            days=days,
            market_type=market_type,
            user_id=user_id
        )
        
        logger.info("✅ Entrenamiento completado exitosamente.")
        logger.info(f"📂 Modelos guardados en: api/data/models/{market_type}/")
        
    except Exception as e:
        logger.error(f"❌ Error crítico durante el entrenamiento: {e}", exc_info=True)

if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
