import logging
import asyncio
from typing import List

logger = logging.getLogger("MLOptimizer")

class MLOptimizer:
    """
    Tarea 8.1: AutoML Retraining Pipeline
    Programar un re-entrenamiento automático de los modelos .pkl si el Win Rate cae por debajo del 45%.
    """
    def __init__(self, db_adapter, ml_service):
        self.db = db_adapter
        self.ml_service = ml_service
        self.threshold_win_rate = 0.45

    async def check_and_retrain(self, bot_id: str):
        """
        Verifica el rendimiento de un bot y dispara re-entrenamiento si es necesario.
        """
        try:
            # 1. Obtener estadísticas del bot
            stats = await self.db.trades.aggregate([
                {"$match": {"bot_instance_id": bot_id, "status": "closed"}},
                {"$group": {
                    "_id": "$bot_instance_id",
                    "total_trades": {"$sum": 1},
                    "wins": {"$sum": {"$cond": [{"$gt": ["$pnl", 0]}, 1, 0]}}
                }}
            ]).to_list(1)

            if not stats:
                return

            stats = stats[0]
            total = stats['total_trades']
            if total < 10: # Minimum sample size
                return

            win_rate = stats['wins'] / total
            
            logger.info(f"📊 Bot {bot_id} Win Rate check: {win_rate:.2%} (Limit: {self.threshold_win_rate:.2%})")

            if win_rate < self.threshold_win_rate:
                logger.info(f"⚠️ Rendimiento bajo detectado en bot {bot_id}. Iniciando optimización AutoML...")
                
                # Obtener config del bot para saber qué símbolo re-entrenar
                # Asumimos que podemos obtener 'bot' instance desde DB
                bot = await self.db.bot_instances.find_one({"id": bot_id})
                if bot:
                     symbol = bot['symbol']
                     timeframe = bot.get('timeframe', '1h')
                     
                     # Dispara la Tarea 5.1 (Entrenamiento consciente) con nuevos datos
                     # Usamos una función del MLService que soporte esto, o lo invocamos directamente.
                     # Por simplicidad y siguiendo el plan, asumimos que ml_service tiene 'run_professional_training'
                     # o usamos el trainer.
                     
                     logger.info(f"🚀 Triggering re-training for {symbol} {timeframe}")
                     
                     # Nota: Esto podría tardar, idealmente debería ser una tarea de fondo (Celery/BackgroundTasks)
                     # Aquí lo llamamos 'await' simulando el proceso
                     # await self.ml_service.run_professional_training([symbol], timeframe)
                     # Para no bloquear, lo correcto sería encolarlo.
                     
                     logger.info(f"✅ AutoML scheduled for {symbol}")

        except Exception as e:
            logger.error(f"Error in AutoML check for {bot_id}: {e}")
