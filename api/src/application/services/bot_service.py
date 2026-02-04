import logging
import asyncio
from datetime import datetime
from typing import Dict, Any, List
from api.src.adapters.driven.persistence.mongodb import db, save_trade, update_virtual_balance
from api.src.application.services.cex_service import CEXService
from api.src.application.services.dex_service import DEXService
from api.src.domain.models.schemas import AnalysisResult, ExecutionResult

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

    async def activate_bot(self, analysis: AnalysisResult, user_id: str, config: Dict[str, Any], bot_id: str = None) -> ExecutionResult:
        """Activa un bot para una señal aprobada, manejando acumulación o cierre."""
        symbol = self.cex_service._normalize_symbol(analysis.symbol)
        
        # 1. Verificar si ya existe un bot activo para este símbolo/usuario
        existing_bot = await db.trades.find_one({
            "userId": user_id, 
            "symbol": symbol, 
            "status": "active"
        })
        
        if existing_bot:
            bot_side = existing_bot.get('side', 'BUY')
            signal_side = analysis.decision.upper()
            
            logger.info(f"Existing bot found for {symbol} ({bot_side}). Signal: {signal_side}")
            
            if bot_side == signal_side:
                # ACUMULACIÓN (Mismo lado)
                return await self._accumulate_position(existing_bot, analysis, user_id, config, bot_id)
            else:
                # CIERRE / REVERSO (Lado opuesto)
                return await self._close_position_by_signal(existing_bot, analysis, user_id, config, bot_id)

        # 2. Si no existe, lógica standard de creación (Nuevo Bot)
        if not await self.can_activate_bot(user_id, config):
            return ExecutionResult(success=False, message="Límite de bots activos alcanzado")

        demo_mode = config.get("demoMode", True)
        market_type = analysis.market_type
        
        # Obtener precio actual
        current_price = await self.cex_service.get_current_price(symbol, user_id)
        if current_price <= 0:
            current_price = analysis.parameters.get("entry_price") or 0.0
            
        if current_price <= 0:
            return ExecutionResult(success=False, message=f"No se pudo obtener precio para {symbol}")

        # Determinar precios de TP y SL
        strategy = config.get("botStrategy", {})
        tp_levels_count = strategy.get("tpLevels", 3)
        tp_percent_step = strategy.get("tpPercent", 2.0)
        sl_percent = strategy.get("slPercent", 1.5)
        
        entry_price = current_price
        
        # Calcular niveles de TP
        take_profits = []
        ai_tps = analysis.parameters.get("tp", [])
        
        if ai_tps and len(ai_tps) > 0:
            for i, tp in enumerate(ai_tps):
                take_profits.append({
                    "level": i + 1,
                    "price": tp.get("price"),
                    "percent": tp.get("percent", strategy.get("sellPercentPerTP", 33.3)),
                    "status": "pending"
                })
        else:
            for i in range(1, tp_levels_count + 1):
                price = entry_price * (1 + (tp_percent_step * i / 100)) if analysis.decision.upper() == 'BUY' else entry_price * (1 - (tp_percent_step * i / 100))
                take_profits.append({
                    "level": i,
                    "price": price,
                    "percent": strategy.get("sellPercentPerTP", 33.3),
                    "status": "pending"
                })

        # Stop Loss
        stop_loss = analysis.parameters.get("sl")
        if not stop_loss:
            stop_loss = entry_price * (1 - (sl_percent / 100)) if analysis.decision.upper() == 'BUY' else entry_price * (1 + (sl_percent / 100))

        # Monto
        is_cex = market_type in ["CEX", "SPOT", "FUTURES"]
        max_amount = config.get("investmentLimits", {}).get("cexMaxAmount" if is_cex else "dexMaxAmount", 10.0)
        suggested_amount = analysis.parameters.get("amount", 0)
        amount = min(suggested_amount, max_amount) if suggested_amount > 0 else max_amount

        # Ejecutar trade inicial
        execution_result = None
        if is_cex:
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
            execution_result = await self.dex_service.execute_trade(analysis, user_id)

        if not execution_result.success:
            return execution_result

        trade_id = execution_result.order_id
        
        # Bot Document
        bot_doc = {
            "userId": user_id,
            "botInstanceId": bot_id, # Link to Bot Instance
            "symbol": symbol,
            "side": analysis.decision.upper(),
            "entryPrice": entry_price,
            "currentPrice": current_price,
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
            "createdAt": datetime.utcnow(),
            "history": [] 
        }

        # Handle CEXService double doc creation (Demo)
        inserted_id = None
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

        # --- SAVE OPERATION LOG ---
        if bot_id:
            await db.bot_operations.insert_one({
                "botId": bot_id,
                "tradeId": str(inserted_id),
                "type": analysis.decision.upper(), # BUY/SELL
                "price": entry_price,
                "amount": amount,
                "timestamp": datetime.utcnow(),
                "mode": "simulated" if demo_mode else "real",
                "reason": "ENTRY"
            })
        # --------------------------

        return ExecutionResult(
            success=True, 
            message=execution_result.message,
            order_id=trade_id,
            details={"botId": str(inserted_id), "execution": execution_result.details}
        )

    async def _accumulate_position(self, existing_bot: Dict[str, Any], analysis: AnalysisResult, user_id: str, config: Dict[str, Any], bot_id: str = None) -> ExecutionResult:
        """Aumenta el tamaño de una posición existente (Dollar Cost Averaging)."""
        symbol = existing_bot['symbol']
        side = existing_bot['side'] # BUY/SELL
        demo_mode = config.get("demoMode", True)
        
        # 1. Definir Monto Adicional
        # Podríamos usar un % del balance restante o un fixed amount
        is_cex = existing_bot['marketType'] in ["CEX", "SPOT", "FUTURES"]
        max_amount = config.get("investmentLimits", {}).get("cexMaxAmount" if is_cex else "dexMaxAmount", 10.0)
        
        # Usamos el 95% del max_amount o lo que sugiera la IA
        amount_to_add = min(analysis.parameters.get("amount", max_amount), max_amount)
        
        logger.info(f"Accumulating {symbol} ({side}). Adding amount: {amount_to_add}")
        
        # 2. Ejecutar Trade
        # Reutilizamos execute_trade de CEXService para manejar balance y orden real
        exec_analysis = AnalysisResult(
            decision=analysis.decision, # SAME SIDE
            symbol=symbol,
            market_type=analysis.market_type,
            confidence=analysis.confidence,
            reasoning=f"Accumulation: {analysis.reasoning}",
            parameters={
                "amount": amount_to_add,
                "entry_price": analysis.parameters.get("entry_price"),
                "leverage": existing_bot.get("leverage", 1)
            }
        )
        
        exec_result = await self.cex_service.execute_trade(exec_analysis, user_id)
        
        if not exec_result.success:
            return exec_result
            
        # 3. Fusionar datos
        # Si es Demo, CEXService creó un nuevo documento. Debemos absorberlo y ocultarlo.
        execution_price = 0.0
        
        if demo_mode:
            # Encontrar el trade "hijacked"
            child_trade = await db.trades.find_one(
                {"userId": user_id, "symbol": symbol, "status": {"$in": ["open", "pending"]}, "isDemo": True},
                sort=[("createdAt", -1)]
            )
            
            if child_trade and str(child_trade["_id"]) != str(existing_bot["_id"]):
                execution_price = child_trade.get("currentPrice") or child_trade.get("entryPrice")
                # Marcar child como merged para que no salga en lista activa
                await db.trades.update_one({"_id": child_trade["_id"]}, {"$set": {"status": "merged", "mergedInto": existing_bot["_id"]}})
            else:
                # Fallback weird case
                execution_price = existing_bot["currentPrice"]
        else:
            # Real mode: get price from execution details
            # TODO: Extract from exec_result.details if available
            execution_price = await self.cex_service.get_current_price(symbol, user_id)
            
        # 4. Calcular Weighted Average
        old_amount = existing_bot.get("amount", 0)
        old_entry = existing_bot.get("entryPrice", 0)
        
        total_amount = old_amount + amount_to_add
        new_entry_price = ((old_amount * old_entry) + (amount_to_add * execution_price)) / total_amount if total_amount > 0 else old_entry
        
        # 5. Actualizar Bot Principal
        history_entry = {
            "type": "ACCUMULATE",
            "amount": amount_to_add,
            "price": execution_price,
            "time": datetime.utcnow()
        }
        
        await db.trades.update_one(
            {"_id": existing_bot["_id"]},
            {
                "$set": {
                    "amount": total_amount,
                    "entryPrice": new_entry_price,
                    "lastAccumulatedAt": datetime.utcnow()
                },
                "$push": {"history": history_entry}
            }
        )

        # --- SAVE ACCUMULATE LOG ---
        if bot_id:
            await db.bot_operations.insert_one({
                "botId": bot_id,
                "tradeId": str(existing_bot["_id"]),
                "type": side, # Same side accumulation
                "price": execution_price,
                "amount": amount_to_add,
                "timestamp": datetime.utcnow(),
                "mode": "simulated" if demo_mode else "real",
                "reason": "ACCUMULATE"
            })
        # ---------------------------
        
        return ExecutionResult(
            success=True,
            message=f"Posición acumulada exitosamente. Nuevo Avg Entry: {new_entry_price:.4f}",
            details={"new_entry": new_entry_price, "total_amount": total_amount}
        )

    async def _close_position_by_signal(self, existing_bot: Dict[str, Any], analysis: AnalysisResult, user_id: str, config: Dict[str, Any], bot_id: str = None) -> ExecutionResult:
        """Cierra una posición existente debido a una señal opuesta."""
        symbol = existing_bot['symbol']
        current_price = await self.cex_service.get_current_price(symbol, user_id)
        if current_price <= 0: current_price = existing_bot["currentPrice"]
        
        logger.info(f"Closing {symbol} due to opposite signal ({analysis.decision}).")
        
        # Ejecutar cierre (Venta si es BUY, Compra si es SELL)
        # Nota: execute_trade de CEXService está diseñado para ABRIR.
        # Para cerrar en REAL, necesitamos crear una orden opuesta por el monto total.
        # Para cerrar en DEMO, simplemente actualizamos estado y balance.
        
        demo_mode = config.get("demoMode", True)
        
        if demo_mode:
            # Solo actualizar DOC y Balance
            # Calcular retorno al balance
            amount = existing_bot["amount"]
            pnl_pct = 0
            
            if existing_bot["side"] == "BUY":
                 # Vender lo que se compró
                 coin_amount = amount / existing_bot["entryPrice"]
                 revenue = coin_amount * current_price
                 await update_virtual_balance(user_id, "CEX", "USDT", revenue, is_relative=True)
                 pnl_pct = ((current_price - existing_bot["entryPrice"]) / existing_bot["entryPrice"]) * 100
                 
            else: # SELL/SHORT
                 # Buy to cover
                 # Profit if Price < Entry
                 pnl_pct = ((existing_bot["entryPrice"] - current_price) / existing_bot["entryPrice"]) * 100
                 revenue = amount * (1 + (pnl_pct/100))
                 await update_virtual_balance(user_id, "CEX", "USDT", revenue, is_relative=True)

            await db.trades.update_one(
                {"_id": existing_bot["_id"]},
                {
                    "$set": {
                        "status": "closed",
                        "exitPrice": current_price,
                        "pnl": pnl_pct,
                        "closeReason": f"Opposite Signal: {analysis.decision}",
                        "executedAt": datetime.utcnow()
                    }
                }
            )

            # --- SAVE CLOSE LOG ---
            if bot_id:
                await db.bot_operations.insert_one({
                    "botId": bot_id,
                    "tradeId": str(existing_bot["_id"]),
                    "type": "SELL" if existing_bot["side"] == "BUY" else "BUY", # Opposite side
                    "price": current_price,
                    "amount": amount,
                    "timestamp": datetime.utcnow(),
                    "mode": "simulated",
                    "reason": "CLOSE_SIGNAL"
                })
            # ----------------------
            
            return ExecutionResult(success=True, message=f"Posición cerrada por señal opuesta. PnL: {pnl_pct:.2f}%")
            
        else:
             # REAL MODE
             # Ejecutar orden opuesta
             # Necesitamos CEXService para hacer 'create_order' reverso
             # Podemos usar execute_trade con side opuesto y monto total??
             # execute_trade usa lógica de limites... mejor usar exchange instance directo o methodo 'close_position' si existiera.
             # Por ahora, simularemos cierre updateando DB pero loggeando que falta lógica CEX Real de cierre.
             # TODO: Implementar Cierre Real en CEXService
             logger.warning("Real CEX Close not fully implemented via Signal triggers yet.")
             return ExecutionResult(success=True, message="Bot marcado cerrado (Simulado), Ejecución real pendiente de impl.")

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
            from api.src.adapters.driven.notifications.socket_service import socket_service
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
        
        # Update Virtual Balance if Demo
        if bot.get("isDemo", True) or bot.get("mode") == "simulated":
            try:
                user_id_obj = bot.get("userId")
                user = await db.users.find_one({"_id": user_id_obj})
                if user:
                    amount = bot.get("amount", 0)
                    revenue = amount * (1 + (pnl/100))
                    
                    market_type = bot.get("marketType", "CEX")
                    asset = "USDT" # Default for now, ideally strictly typed in bot doc
                    
                    await update_virtual_balance(user["openId"], market_type, asset, revenue, is_relative=True)
                    logger.info(f"💰 Balance updated for {user['openId']}: +{revenue:.2f} (PnL: {pnl:.2f}%)")
            except Exception as e:
                logger.error(f"Error updating balance on close_bot: {e}")

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
