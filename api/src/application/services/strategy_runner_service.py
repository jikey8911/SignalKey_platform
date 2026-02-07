
import asyncio
import logging
import traceback
from datetime import datetime
from typing import List, Dict, Any

from api.src.adapters.driven.persistence.mongodb import db, get_app_config
from api.src.application.services.ml_service import MLService
from api.src.application.services.bot_service import SignalBotService
from api.src.domain.models.schemas import AnalysisResult, TradingSignal
from api.src.adapters.driven.notifications.socket_service import socket_service
from api.src.application.services.buffer_service import DataBufferService

logger = logging.getLogger(__name__)

class StrategyRunnerService:
    """
    Servicio de Segundo Plano (Sprint 5/6)
    Responsable de iterar sobre bots activos, obtener datos de mercado frescos,
    ejecutar modelos de estrategia y activar señales resultantes.
    """
    def __init__(self, ml_service: MLService, bot_service: SignalBotService):
        self.ml_service = ml_service
        self.bot_service = bot_service
        self.running = False
        self.interval = 60 # Default loop interval (seconds)

    async def start(self):
        if self.running: return
        self.running = True
        logger.info("🚀 StrategyRunnerService Iniciado.")
        
        try:
            while self.running:
                try:
                    await self._run_cycle()
                except Exception as e:
                    logger.error(f"Error crítico en Strategy Runner loop: {e}")
                    traceback.print_exc()
                
                await asyncio.sleep(self.interval)
        except asyncio.CancelledError:
            logger.info("🛑 StrategyRunnerService Cancelado (Shutdown).")
            self.running = False
        finally:
            self.running = False

    async def stop(self):
        self.running = False
        logger.info("🛑 StrategyRunnerService Detenido.")

    async def _run_cycle(self):
        # 1. Obtener Bots Activos (Configuraciones de Bot)
        # Iteramos sobre todas las instancias de bot marcadas como 'active'
        cursor = db.bot_instances.find({"status": "active"})
        active_bots = await cursor.to_list(length=100)
        
        if not active_bots:
            return

        logger.debug(f"StrategyRunner: Analizando {len(active_bots)} bots activos...")

        processed_symbols = set()

        for bot in active_bots:
            try:
                symbol = bot.get('symbol')
                user_open_id = bot.get('user_id') # BotInstance stores openId directly usually, let's verify
                # MongoBotRepository saves user_id which comes from current_user["openId"] in bot_router.py
                # So here 'user_id' IS the openId.
                
                strategy_name = bot.get('strategy_name', 'auto')
                timeframe = bot.get('timeframe', '1h')
                
                # Evitar procesar mismo símbolo/usuario múltiples veces si hay duplicados
                bot_key = f"{user_open_id}_{symbol}"
                if bot_key in processed_symbols: continue
                processed_symbols.add(bot_key)

                # 2. Obtener Configuración de App del Usuario
                config = await get_app_config(user_open_id)
                if not config or not config.get('isAutoEnabled', False):
                    # Skip si auto trading global deshabilitado para usuario
                    continue

                # 3. Verificar estado actual (¿Tiene trade abierto este bot?)
                # Buscamos trade activo para este usuario y símbolo
                # Nota: Asumimos un trade activo por símbolo/bot por ahora.
                current_trade = await db.trades.find_one({
                    "userId": config.get("userId"), # Trade usa ObjectId reference usually?
                    # Wait, saving trade uses config["userId"] which is ObjectId string or obj? 
                    # Let's check save_trade in CEXService. It uses config["userId"].
                    # config["userId"] comes from user["_id"].
                    # So we need user's ObjectId.
                    
                    # Alternative: We can search by symbol and status="open" / "active" and correlate.
                    # Let's look up user to get _id
                     "symbol": symbol,
                     "status": {"$in": ["open", "active", "pending"]}
                })
                
                # If we didn't find by userId in config, maybe we need to fetch user first to be sure
                if not current_trade:
                     user_doc = await db.users.find_one({"openId": user_open_id})
                     if user_doc:
                         current_trade = await db.trades.find_one({
                             "userId": user_doc["_id"], # ObjectId
                             "symbol": symbol,
                             "status": {"$in": ["open", "active", "pending"]}
                         })

                # 4. Obtener Datos de Mercado Recientes (Optimized via DataBuffer)
                candles_df = None
                buffer_data = DataBufferService().get_latest_data("binance", symbol, timeframe)  # Assuming binance for now or use bot.exchangeId
                
                if buffer_data is not None and len(buffer_data) >= 50:
                    candles_df = buffer_data.tail(100) # Get last 100
                
                if candles_df is None or candles_df.empty:
                     # Fallback to API if buffer empty or insufficient
                     candles_df = await self.ml_service.exchange.get_public_historical_data(
                        symbol=symbol,
                        timeframe=timeframe,
                        limit=100,
                        user_id=user_open_id
                    )
                
                if candles_df.empty:
                    continue

                candles_list = candles_df.reset_index().to_dict('records')
                
                # 5. Configurar Posición Actual para el Modelo
                current_position = None
                if current_trade:
                    current_position = {
                        "qty": current_trade.get('amount', 0),
                        "avg_price": current_trade.get('entryPrice', 0),
                        "side": current_trade.get('side', 'BUY') # Default to BUY side (Long) if unsure, usually 'BUY' or 'SELL'
                    }
                
                # 6. Ejecutar Predicción
                prediction = self.ml_service.predict(
                    symbol=symbol,
                    timeframe=timeframe,
                    candles=candles_list,
                    market_type=bot.get('market_type', 'spot'),
                    strategy_name=strategy_name,
                    current_position=current_position
                )
                
                decision = prediction.get('decision', 'HOLD')
                
                # 7. Persistencia y Emisión de Señal (Tarea 4.3/4.5: Emitir HOLD y otros)
                confidence = prediction.get('confidence', 0.85)
                try:
                    from api.src.domain.entities.signal import Signal, SignalStatus, Decision, MarketType
                    from api.src.adapters.driven.persistence.mongodb_signal_repository import MongoDBSignalRepository
                    
                    signal_repo = MongoDBSignalRepository(db)
                    
                    # Determinar estado
                    sig_status = SignalStatus.EXECUTED if decision in ['BUY', 'SELL'] else SignalStatus.ACCEPTED
                    if decision == 'HOLD':
                         sig_status = SignalStatus.ACCEPTED # O un estado específico para HOLD si se desea
                    
                    sig_entity = Signal(
                        id=None,
                        userId=user_open_id,
                        source=f"AUTO_STRATEGY_{strategy_name.upper()}",
                        rawText=f"Auto generated signal {decision}",
                        status=sig_status,
                        createdAt=datetime.utcnow(),
                        symbol=symbol,
                        marketType=MarketType(bot.get('market_type', 'spot').upper()),
                        decision=Decision(decision),
                        confidence=confidence,
                        reasoning=f"Strategy: {prediction.get('strategy_used')}",
                        botId=str(bot.get('_id'))
                    )
                    
                    await signal_repo.save(sig_entity)
                    
                    # --- WEBSOCKET EMISSION ---
                    await socket_service.emit_to_user(user_open_id, "signal_update", sig_entity.to_dict())
                    # --------------------------
                    
                except Exception as e:
                    logger.error(f"Error saving/emitting signal: {e}")

                # 8. Actuar si es una señal ejecutable
                if decision in ['BUY', 'SELL']:
                    analysis = AnalysisResult(
                        symbol=symbol,
                        decision=decision,
                        market_type=bot.get('market_type', 'spot'),
                        confidence=confidence,
                        reasoning=f"Auto Strategy Runner ({prediction.get('strategy_used')})",
                        parameters={
                            "price": candles_list[-1]['close'],
                            "amount": bot.get('amount')
                        }
                    )
                    logger.info(f"🤖 AutoSignal: {decision} for {symbol} (User: {user_open_id})")
                    await self.bot_service.activate_bot(analysis, user_open_id, config, bot_id=str(bot.get('_id')))

            except Exception as e:
                logger.error(f"Error procesando bot {bot.get('_id')}: {e}")
