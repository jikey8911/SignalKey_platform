import logging
import asyncio
from datetime import datetime
from typing import Dict, Any, List
from src.adapters.driven.persistence.mongodb import db, save_trade, update_virtual_balance
from src.application.services.cex_service import CEXService
from src.application.services.dex_service import DEXService
from src.domain.models.schemas import AnalysisResult, ExecutionResult

logger = logging.getLogger(__name__)

class SignalBotService:
    def __init__(self, cex_service: CEXService = None, dex_service: DEXService = None):
        self.cex_service = cex_service or CEXService()
        self.dex_service = dex_service or DEXService()

    async def can_activate_bot(self, user_id: str, config: Dict[str, Any]) -> bool:
        """Verifica si el usuario puede activar un nuevo bot basado en su límite."""
        max_bots = config.get("botStrategy", {}).get("maxActiveBots", 5)
        active_bots_count = await db.trades.count_documents({
            "userId": user_id,
            "status": "active"
        })
        return active_bots_count < max_bots

    async def activate_bot(self, analysis: AnalysisResult, user_id: str, config: Dict[str, Any]) -> ExecutionResult:
        """Activa un bot para una señal aprobada."""
        if not await self.can_activate_bot(user_id, config):
            return ExecutionResult(success=False, message="Límite de bots activos alcanzado")

        demo_mode = config.get("demoMode", True)
        market_type = analysis.market_type # "CEX", "FUTURES" o "DEX"
        
        # Normalizar símbolo usando CEXService
        symbol = self.cex_service._normalize_symbol(analysis.symbol)
        
        # Obtener precio actual real para la entrada
        current_price = await self.cex_service.get_current_price(symbol, user_id)
        if current_price <= 0:
            # Fallback a precio de la IA si no se puede obtener el real
            current_price = analysis.parameters.get("entry_price") or 0.0
            
        if current_price <= 0:
            return ExecutionResult(success=False, message=f"No se pudo obtener precio para {symbol}")

        # Determinar precios de TP y SL
        # Prioridad: 1. Parámetros de la IA, 2. Configuración de estrategia del bot
        strategy = config.get("botStrategy", {})
        tp_levels_count = strategy.get("tpLevels", 3)
        tp_percent_step = strategy.get("tpPercent", 2.0)
        sl_percent = strategy.get("slPercent", 1.5)
        
        entry_price = current_price
        
        # Calcular niveles de TP
        take_profits = []
        ai_tps = analysis.parameters.get("tp", [])
        
        if ai_tps and len(ai_tps) > 0:
            # Usar TPs de la IA si vienen definidos
            for i, tp in enumerate(ai_tps):
                take_profits.append({
                    "level": i + 1,
                    "price": tp.get("price"),
                    "percent": tp.get("percent", strategy.get("sellPercentPerTP", 33.3)),
                    "status": "pending"
                })
        else:
            # Generar TPs basados en porcentajes de configuración
            for i in range(1, tp_levels_count + 1):
                price = entry_price * (1 + (tp_percent_step * i / 100))
                take_profits.append({
                    "level": i,
                    "price": price,
                    "percent": strategy.get("sellPercentPerTP", 33.3),
                    "status": "pending"
                })

        # Stop Loss
        stop_loss = analysis.parameters.get("sl") or (entry_price * (1 - (sl_percent / 100)))

        # Monto de inversión
        is_cex = market_type in ["CEX", "SPOT", "FUTURES"]
        max_amount = config.get("investmentLimits", {}).get("cexMaxAmount" if is_cex else "dexMaxAmount", 10.0)
        suggested_amount = analysis.parameters.get("amount", 0)
        amount = min(suggested_amount, max_amount) if suggested_amount > 0 else max_amount

        # Ejecutar trade inicial (Market Buy/Sell)
        # Esto manejará tanto Demo como Real a través de CEXService/DEXService
        execution_result = None
        if is_cex:
            # Crear un AnalysisResult parcial para execute_trade
            exec_analysis = AnalysisResult(
                decision=analysis.decision,
                symbol=symbol,
                market_type=analysis.market_type,
                confidence=analysis.confidence,
                reasoning=analysis.reasoning,
                parameters={
                    "entry_price": entry_price,
                    "amount": amount,
                    "tp": analysis.parameters.get("tp", []),
                    "sl": analysis.parameters.get("sl"),
                    "leverage": analysis.parameters.get("leverage", 1)
                }
            )
            execution_result = await self.cex_service.execute_trade(exec_analysis, user_id)
        else:
            # Para DEX usamos dex_service
            execution_result = await self.dex_service.execute_trade(analysis, user_id)

        if not execution_result.success:
            return execution_result

        # El bot creado por cex_service.execute_trade ya está en la DB si era Demo
        # Pero SignalBotService crea bots más complejos (con múltiples TP/SL)
        # BUG POTENCIAL: CEXService crea un trade doc y SignalBotService crea otro.
        # SOLUCIÓN: Si CEXService ya lo creó, lo actualizamos con los campos extra.
        # O mejor: SignalBotService hereda el trade creado o actualiza el existente.
        
        # Para evitar duplicados en Demo (que CEXService guarda), buscamos el último guardado
        # o simplemente pasamos el ID si pudiéramos.
        # Por simplicidad en este sprint: Borramos el simplificado y guardamos el completo 
        # o actualizamos el que creó CEXService si es demo.
        
        trade_id = execution_result.order_id # En demo, order_id suele ser nulo o el string de info
        
        # Enriquecer el documento para el monitoreo avanzado
        bot_doc = {
            "userId": user_id,
            "symbol": symbol,
            "side": analysis.decision.upper(),
            "entryPrice": entry_price,
            "currentPrice": entry_price,
            "stopLoss": stop_loss,
            "takeProfits": take_profits,
            "amount": amount,
            "leverage": analysis.parameters.get("leverage", 1),
            "marketType": market_type,
            "isDemo": demo_mode,
            "status": "active",
            "orderId": trade_id,
            "currentTPLevel": 0,
            "pnl": 0.0,
            "createdAt": datetime.utcnow()
        }

        # Si CEXService ya guardó un doc (por ser demo), lo actualizamos en lugar de crear uno nuevo
        if demo_mode:
            # Buscar el trade que acaba de crear CEXService
            last_demo = await db.trades.find_one(
                {"userId": user_id, "symbol": symbol, "status": {"$in": ["open", "pending"]}, "isDemo": True},
                sort=[("createdAt", -1)]
            )
            if last_demo:
                await db.trades.update_one({"_id": last_demo["_id"]}, {"$set": bot_doc})
                inserted_id = last_demo["_id"]
            else:
                inserted_id = await save_trade(bot_doc)
        else:
            inserted_id = await save_trade(bot_doc)

        return ExecutionResult(
            success=True, 
            message=execution_result.message,
            order_id=trade_id,
            details={"botId": str(inserted_id), "execution": execution_result.details}
        )

    async def monitor_bots(self):
        """Proceso en segundo plano para monitorear y actualizar bots activos."""
        while True:
            try:
                active_bots = await db.trades.find({"status": "active"}).to_list(length=100)
                
                # Tiempo de espera por defecto
                next_sleep = 60
                
                for bot in active_bots:
                    # El proceso del tick ahora retorna la distancia mínima al objetivo (%)
                    min_dist = await self._process_bot_tick(bot)
                    
                    # Ajustar el tiempo de espera del siguiente ciclo basado en la cercanía
                    # de CUALQUIER bot a su objetivo
                    if min_dist < 2.0:
                        next_sleep = min(next_sleep, 5)
                    elif min_dist < 5.0:
                        next_sleep = min(next_sleep, 20)
                
                logger.debug(f"Monitor bots cycle complete. Sleeping for {next_sleep}s")
                await asyncio.sleep(next_sleep)
            except Exception as e:
                logger.error(f"Error en monitor_bots: {e}")
                await asyncio.sleep(60) 

    async def _process_bot_tick(self, bot: Dict[str, Any]) -> float:
        """
        Actualiza el estado de un bot individual basado en el precio actual.
        Retorna la distancia porcentual mínima al objetivo más cercano (TP o SL).
        """
        symbol = bot["symbol"]
        current_price = await self._get_current_price(bot)
        
        if current_price <= 0:
            return 100.0 # No hay precio disponible, no aceleramos
            
        # Calcular P&L actual
        entry_price = bot["entryPrice"]
        side = bot.get("side", "BUY")
        
        if side == "BUY":
            pnl = ((current_price - entry_price) / entry_price) * 100
        else:
            pnl = ((entry_price - current_price) / entry_price) * 100
            
        # 1. ACTUALIZAR BASE DE DATOS Y EMITIR POR SOCKET SIEMPRE
        try:
            await db.trades.update_one(
                {"_id": bot["_id"]},
                {"$set": {
                    "currentPrice": current_price,
                    "pnl": pnl,
                    "lastMonitoredAt": datetime.utcnow()
                }}
            )
            
            # Emitir actualización en tiempo real
            from src.adapters.driven.notifications.socket_service import socket_service
            user = await db.users.find_one({"_id": bot["userId"]})
            if user:
                await socket_service.emit_to_user(user["openId"], "bot_update", {
                    "id": str(bot["_id"]),
                    "symbol": symbol,
                    "currentPrice": current_price,
                    "pnl": pnl,
                    "status": bot["status"]
                })
        except Exception as e:
            logger.error(f"Error updating bot tick for {bot['_id']}: {e}")

        # 2. CALCULAR DISTANCIAS A OBJETIVOS PARA FRECUENCIA DINÁMICA
        # Distancia al Stop Loss
        dist_sl = abs(current_price - bot["stopLoss"]) / current_price * 100
        
        # Distancia al siguiente Take Profit pendiente
        dist_tp = 100.0
        pending_tps = [tp for tp in bot["takeProfits"] if tp["status"] == "pending"]
        if pending_tps:
            # Encontrar el TP más cercano al precio actual
            closest_tp_price = min([tp["price"] for tp in pending_tps]) if side == "BUY" else max([tp["price"] for tp in pending_tps])
            dist_tp = abs(current_price - closest_tp_price) / current_price * 100
            
        min_dist = min(dist_sl, dist_tp)

        # 3. VERIFICAR EJECUCIÓN (TP/SL)
        # Verificar Stop Loss
        if (side == "BUY" and current_price <= bot["stopLoss"]) or (side == "SELL" and current_price >= bot["stopLoss"]):
            await self._close_bot(bot, current_price, "failed", "Stop Loss alcanzado")
            return min_dist

        # Verificar Take Profits
        updated_tps = bot["takeProfits"]
        any_tp_hit = False
        for tp in updated_tps:
            is_hit = (side == "BUY" and current_price >= tp["price"]) or (side == "SELL" and current_price <= tp["price"])
            if tp["status"] == "pending" and is_hit:
                tp["status"] = "hit"
                tp["hitAt"] = datetime.utcnow()
                bot["currentTPLevel"] = tp["level"]
                any_tp_hit = True
                logger.info(f"Bot {bot['_id']} alcanzó TP Nivel {tp['level']} para {symbol} (MARKET EXECUTION)")

        if any_tp_hit:
            # Si todos los TP se alcanzaron, cerrar bot
            if all(tp["status"] == "hit" for tp in updated_tps):
                await self._close_bot(bot, current_price, "completed", "Todos los TP alcanzados")
            else:
                await db.trades.update_one(
                    {"_id": bot["_id"]},
                    {"$set": {"takeProfits": updated_tps, "currentTPLevel": bot["currentTPLevel"]}}
                )
        
        return min_dist

    async def _get_current_price(self, bot: Dict[str, Any]) -> float:
        """Obtiene el precio actual real usando CEXService."""
        user = await db.users.find_one({"_id": bot["userId"]})
        user_id = user["openId"] if user else "default_user"
        return await self.cex_service.get_current_price(bot["symbol"], user_id)

    async def _close_bot(self, bot: Dict[str, Any], exit_price: float, status: str, reason: str):
        pnl = ((exit_price - bot["entryPrice"]) / bot["entryPrice"]) * 100
        await db.trades.update_one(
            {"_id": bot["_id"]},
            {
                "$set": {
                    "status": status,
                    "exitPrice": exit_price,
                    "pnl": pnl,
                    "closeReason": reason,
                    "executedAt": datetime.utcnow()
                }
            }
        )
        logger.info(f"Bot {bot['_id']} cerrado: {status} ({reason}). PnL: {pnl:.2f}%")
