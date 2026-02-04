import asyncio
import logging
from datetime import datetime
from api.src.adapters.driven.persistence.mongodb_bot_repository import MongoBotRepository
from api.src.application.services.ml_service import MLService
from api.src.application.services.execution_engine import ExecutionEngine
from api.src.adapters.driven.exchange.ccxt_adapter import ccxt_service
from api.src.domain.strategies.base import BaseStrategy

logger = logging.getLogger("StrategyRunner")

class StrategyRunnerService:
    """
    Servicio autónomo que ejecuta el ciclo de vida de los bots activos:
    1. Obtener Bots Activos
    2. Obtener Market Data (Velas)
    3. Inferencia ML (Generar Señal)
    4. Ejecución (ExecutionEngine)
    """
    def __init__(self, bot_repo: MongoBotRepository, ml_service: MLService, execution_engine: ExecutionEngine):
        self.bot_repo = bot_repo
        self.ml_service = ml_service
        self.engine = execution_engine
        self.running = False
        self.task = None

    async def start(self):
        if self.running: return
        self.running = True
        self.task = asyncio.create_task(self._loop())
        logger.info("StrategyRunnerService started.")

    async def stop(self):
        self.running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        logger.info("StrategyRunnerService stopped.")

    async def _loop(self):
        while self.running:
            try:
                # 1. Obtener bots activos (Autotrade enabled)
                # Filter by status='active' AND global checks if needed
                active_bots = await self.bot_repo.get_active_bots()
                
                if not active_bots:
                    await asyncio.sleep(10)
                    continue

                logger.info(f"StrategyRunner: Processing {len(active_bots)} active bots...")

                for bot in active_bots:
                    try:
                        await self._process_bot(bot)
                    except Exception as e:
                        logger.error(f"Error processing bot {bot.name} ({bot.symbol}): {e}")

                # Wait before next cycle (e.g. 60s or dynamic based on timeframe)
                # For now, 60s is safe for 1m+ timeframes.
                await asyncio.sleep(60)

            except Exception as e:
                logger.error(f"Error in StrategyRunner loop: {e}")
                await asyncio.sleep(60)

    async def _process_bot(self, bot):
        # 2. Obtener Market Data
        # Retrieve user config to determine correct exchange
        from api.src.adapters.driven.persistence.mongodb import get_app_config
        
        exchange_id = "binance" # Fallback
        try:
            config = await get_app_config(bot.user_id)
            if config and "exchanges" in config:
                # Find active exchange or first one
                active_ex = next((e for e in config["exchanges"] if e.get("isActive")), None)
                if active_ex:
                    exchange_id = active_ex.get("exchangeId", "binance")
        except Exception as e:
            logger.warning(f"Failed to fetch user config for bot {bot.id}, defaulting to binance: {e}")

        # Fetch enough candles for the model (e.g. 100)
        # Using configured exchange
        candles_df = await ccxt_service.get_public_historical_data(
            bot.symbol, 
            bot.timeframe, 
            limit=100,
            exchange_id=exchange_id 
        )
        
        if candles_df.empty:
            logger.warning(f"No candles found for {bot.symbol} on {exchange_id}")
            return

        # Convert to list of dicts for MLService (assuming it expects that or DF)
        # MLService.predict takes list of dicts or deals with it.
        # Let's check MLService.predict signature: def predict(self, symbol, timeframe, candles: List[Dict], ...)
        
        candles_list = []
        for ts, row in candles_df.iterrows():
             # TS in index is datetime64
             item = row.to_dict()
             item['time'] = ts.isoformat()
             candles_list.append(item)

        # 3. Inferencia ML
        prediction = self.ml_service.predict(
            symbol=bot.symbol,
            timeframe=bot.timeframe,
            candles=candles_list,
            strategy_name=bot.strategy_name
        )
        
        # decision: "BUY", "SELL", "HOLD"
        decision = prediction.get("decision", "HOLD")
        
        signal_int = 0
        if decision == "BUY": signal_int = BaseStrategy.SIGNAL_BUY
        elif decision == "SELL": signal_int = BaseStrategy.SIGNAL_SELL
        
        if signal_int == 0:
            return # No signal, do nothing

        logger.info(f"Signal generated for {bot.symbol}: {decision}")

        # 4. Ejecución
        current_price = candles_df.iloc[-1]['close'] # Estimation
        
        # We need to pass the bot document (as dict) to engine. 
        # bot is BotInstance object. to_dict() handling needed?
        # Engine expects dict access: bot_instance['status']
        bot_dict = bot.to_dict()
        bot_dict['_id'] = bot.id # Ensure ID is present for engine updates
        
        await self.engine.process_signal(
            bot_instance=bot_dict, 
            signal_data={
                "signal": signal_int,
                "price": current_price
            }
        )
