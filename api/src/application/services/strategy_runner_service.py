
import asyncio
import logging
import traceback
from datetime import datetime
from typing import List, Dict, Any

from api.src.adapters.driven.persistence.mongodb import db, get_app_config
from api.src.application.services.ml_service import MLService
from api.src.application.services.bot_service import SignalBotService
from api.src.domain.models.schemas import AnalysisResult, TradingSignal

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
        # 1. Obtener Bots Activos (que no estén cerrados, obviously)
        # Nota: Buscamos bots marcados como 'active'.
        # Idealmente iteraríamos por *Configuraciones* de Bot, pero en este MVP
        # los bots activos en 'trades' actúan como instancias persistentes de monitoreo.
        # Si queremos que el bot genere NUEVAS señales (flipping, re-entry), debemos mirar también
        # los bots que están en estado "active" (monitoreando salida) O configuraciones de usuario.
        
        # Para simplificar: Iteramos sobre todos los documentos en 'trades' con status 'active'.
        # Esto asume que un "Bot Instance" se mantiene vivo para recibir nuevas señales 
        # (p.ej. para invertir posición).
        
        cursor = db.trades.find({"status": "active"})
        active_bots = await cursor.to_list(length=100)
        
        if not active_bots:
            return

        logger.debug(f"StrategyRunner: Analizando {len(active_bots)} bots activos...")

        processed_symbols = set()

        for bot in active_bots:
            try:
                symbol = bot.get('symbol')
                user_id_obj = bot.get('userId') # ObjectId
                strategy_name = bot.get('strategy_name', 'auto') # Asumir nombre estrategia guardado
                timeframe = bot.get('timeframe', '1h')
                
                # Evitar procesar mismo símbolo/usuario múltiples veces si hay duplicados
                bot_key = f"{user_id_obj}_{symbol}"
                if bot_key in processed_symbols: continue
                processed_symbols.add(bot_key)

                # 2. Obtener Usuario y Config
                user = await db.users.find_one({"_id": user_id_obj})
                if not user: continue
                user_open_id = user['openId']

                config = await get_app_config(user_open_id)
                if not config or not config.get('isAutoEnabled', False):
                    # Skip si auto trading global deshabilitado para usuario
                    continue

                # 3. Obtener Datos de Mercado Recientes (ML Service usa exchange adapter inside)
                # Necesitamos pasar las velas al predict.
                # MLService.predict espera `candles`.
                
                # Fetch candles via Exchange Adapter (accediendo via MLService.exchange)
                # Usamos el exchange configurado del usuario
                candles_df = await self.ml_service.exchange.get_public_historical_data(
                    symbol=symbol,
                    timeframe=timeframe,
                    limit=100, # Necesitamos suficientes para features
                    user_id=user_open_id
                )
                
                if candles_df.empty:
                    continue

                # Convertir DF a lista de dicts para predict
                candles_list = candles_df.reset_index().to_dict('records')
                # Renombrar timestamp si necesario (MLService espera dicts)
                
                # 4. Ejecutar Predicción
                current_position = {
                    "qty": bot.get('amount', 0), # Simplificado
                    "avg_price": bot.get('entryPrice', 0),
                    "side": bot.get('side')
                }
                
                prediction = self.ml_service.predict(
                    symbol=symbol,
                    timeframe=timeframe,
                    candles=candles_list,
                    market_type=bot.get('marketType', 'spot'),
                    strategy_name='auto', # O bot.strategy_name si existiera
                    current_position=current_position
                )
                
                decision = prediction.get('decision', 'HOLD')
                
                # 5. Actuar sobre la señal
                if decision in ['BUY', 'SELL']:
                    confidence = 0.85 # Placeholder, MLService debería retornarlo
                    
                    # Verificar si la decisión difiere del estado actual o es re-entry
                    # SignalBotService.activate_bot maneja la lógica de "Exists -> Accumulate/Close"
                    
                    analysis = AnalysisResult(
                        symbol=symbol,
                        decision=decision,
                        market_type=bot.get('marketType', 'spot'),
                        confidence=confidence,
                        reasoning=f"Auto Strategy Runner ({prediction.get('strategy_used')})",
                        parameters={
                            "price": candles_list[-1]['close'], # Precio actual aprox
                            "amount": bot.get('amount') # Usar monto del bot o default config
                        }
                    )
                    
                    logger.info(f"🤖 AutoSignal: {decision} for {symbol} (User: {user_open_id})")
                    
                    await self.bot_service.activate_bot(analysis, user_open_id, config)

            except Exception as e:
                logger.error(f"Error procesando bot {bot.get('_id')}: {e}")
