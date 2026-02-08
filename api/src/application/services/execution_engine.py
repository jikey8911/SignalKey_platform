import logging
import asyncio
from datetime import datetime
from bson import ObjectId
from api.src.application.services.simulation_service import SimulationService
from api.src.domain.strategies.base import BaseStrategy

class ExecutionEngine:
    """
    Motor central del Sprint 4. Orquesta la ejecución basándose en el modo (Real/Sim).
    Implementa la Tarea 4.3: Emisión de eventos para el monitoreo híbrido en tiempo real.
    """
    def __init__(self, db_adapter, socket_service=None, exchange_adapter=None):
        self.db = db_adapter
        self.socket = socket_service # Referencia para emitir eventos vía WebSockets hacia el frontend
        self.simulator = SimulationService(db_adapter)

        # Inyección de dependencia (Puerto)
        if exchange_adapter:
             self.real_exchange = exchange_adapter
        else:
             # Fallback temporal para evitar roturas si no se inyecta
             from api.src.adapters.driven.exchange.ccxt_adapter import ccxt_service
             self.real_exchange = ccxt_service

        self.logger = logging.getLogger("ExecutionEngine")

    async def process_signal(self, bot_instance, signal_data):
        """
        Procesa una señal entrante. Soporta DCA, Flip y Open.
        """
        if bot_instance.get('status') != 'active':
            return None

        # 1. Definir variables clave
        mode = bot_instance.get('mode', 'simulated')
        symbol = bot_instance['symbol']
        price = signal_data['price']
        signal = signal_data['signal']
        is_alert = signal_data.get('is_alert', False)
        
        # Validar Amount
        amount = bot_instance.get('amount', 0)
        if amount <= 0:
             amount = 100.0 # Fallback safety net

        # Check Limits & Risk
        if not await self._check_risk_and_balance(bot_instance, amount, price):
             return {"status": "blocked", "reason": "insufficient_balance_or_risk"}

        # 2. Analizar Estado Actual
        current_pos = bot_instance.get('position', {})
        current_qty = float(current_pos.get('qty', 0))
        current_side = bot_instance.get('side') # "BUY" / "SELL"
        signal_side = "BUY" if signal == 1 else "SELL"

        # Profit Guard (Only if not alert)
        if not is_alert and not await self._apply_profit_guard(bot_instance, signal, price):
            return {"status": "blocked", "reason": "profit_guard"}

        # 3. Determinar Acción Lógica
        action = "OPEN"
        if current_qty > 0:
            if current_side == signal_side:
                action = "DCA"
            else:
                action = "FLIP"

        self.logger.info(f"🤖 Engine: {symbol} | Mode: {mode} | Action: {action} | Side: {signal_side}")

        # 4. Ejecución (Real o Simulada)
        execution_result = None

        if mode == 'simulated':
            execution_result = await self._execute_simulated(bot_instance, action, signal_side, price, amount)
        else:
            # En REAL, pasamos la 'action' para que el método sepa si cerrar primero
            execution_result = await self._execute_real(bot_instance, action, signal_side, price, amount)

        # 5. Persistencia (Logs y Webhooks)
        await self._persist_signal(bot_instance, signal_data)

        if execution_result and execution_result.get('success'):
            await self._persist_operation(bot_instance, signal_data, execution_result)

        return execution_result

    async def _persist_signal(self, bot_instance, signal_data):
        """Persiste la señal técnica recibida."""
        try:
            from api.src.domain.entities.signal import Signal, SignalStatus, Decision
            from api.src.adapters.driven.persistence.mongodb_signal_repository import MongoDBSignalRepository
            signal_repo = MongoDBSignalRepository(self.db)
            
            strategy_name = bot_instance.get('strategy_name', 'AUTO_STRATEGY')
            source = f"AUTO_STRATEGY_{strategy_name.upper()}" if strategy_name != 'AUTO_STRATEGY' else "AUTO_STRATEGY"
            
            from api.src.domain.entities.signal import MarketType
            market_type_str = bot_instance.get('market_type') or bot_instance.get('marketType') or 'SPOT'
            
            new_sig = Signal(
                id=None,
                userId=str(bot_instance.get('user_id')),
                source=source,
                rawText=signal_data.get('rawText') or f"Signal {signal_data['signal']} at {signal_data['price']}",
                status=SignalStatus.EXECUTING,
                createdAt=datetime.utcnow(),
                symbol=bot_instance['symbol'],
                marketType=MarketType(market_type_str.upper()),
                decision=Decision.BUY if signal_data['signal'] == 1 else Decision.SELL,
                confidence=signal_data.get('confidence'),
                reasoning=signal_data.get('reasoning'),
                botId=str(bot_instance.get('id') or bot_instance.get('_id'))
            )
            await signal_repo.save(new_sig)
        except Exception as e:
            self.logger.error(f"Error persistiendo señal: {e}")

    async def _update_simulation_position_db(self, bot_instance, action, side, exec_price, exec_qty, exec_amount):
        """
        Maneja la lógica matemática avanzada de la posición simulada y actualiza la colección 'positions'.
        """
        bot_id = bot_instance['_id']
        symbol = bot_instance['symbol']
        user_id = bot_instance['user_id']
        
        # 1. Buscar la posición activa en la nueva colección
        positions_coll = self.db.db["positions"]
        position = await positions_coll.find_one({
            "botId": ObjectId(bot_id),
            "status": "OPEN"
        })

        # Valores iniciales si no existe
        if not position:
            position = {
                "botId": ObjectId(bot_id),
                "userId": user_id,
                "symbol": symbol,
                "status": "OPEN",
                "side": side,
                "currentQty": 0.0,
                "avgEntryPrice": 0.0,
                "investedAmount": 0.0,
                "totalTrades": 0,
                "realizedPnl": 0.0,
                "roi": 0.0
            }

        # 2. Lógica Matemática según la Acción
        prev_qty = float(position["currentQty"])
        prev_avg = float(position["avgEntryPrice"])
        prev_invested = float(position["investedAmount"])
        
        # Si es FLIP, cerramos la anterior (lógica simplificada: reinicio)
        if action == "FLIP":
            # Aquí podrías marcar la anterior como CLOSED y crear una nueva
            await positions_coll.update_one(
                {"_id": position.get("_id")}, 
                {"$set": {"status": "CLOSED", "closedAt": datetime.utcnow()}}
            )
            # Reiniciamos el objeto para la nueva posición
            position["currentQty"] = 0.0
            position["avgEntryPrice"] = 0.0
            position["investedAmount"] = 0.0
            position["totalTrades"] = 0
            position["side"] = side
            prev_qty = 0.0 # Reset para el cálculo siguiente

        # Calcular nuevos valores
        # NOTA: Asumimos que 'side' es la dirección de la señal.
        # Si la posición es LONG y la señal es BUY -> Aumenta posición (DCA)
        # Si la posición es LONG y la señal es SELL -> Disminuye posición (Take Profit / Cierre parcial)
        
        is_increasing_position = (position["side"] == side) or (prev_qty == 0)

        if is_increasing_position:
            # --- COMPRA / AUMENTO (DCA) ---
            new_qty = prev_qty + exec_qty
            total_cost = (prev_qty * prev_avg) + (exec_qty * exec_price)
            new_avg_price = total_cost / new_qty if new_qty > 0 else exec_price
            
            position["currentQty"] = new_qty
            position["avgEntryPrice"] = new_avg_price
            position["investedAmount"] = total_cost
            position["totalTrades"] += 1
            
        else:
            # --- VENTA / REDUCCIÓN ---
            trade_pnl = 0
            if position["side"] == "BUY": # Long
                trade_pnl = (exec_price - prev_avg) * exec_qty
            else: # Short
                trade_pnl = (prev_avg - exec_price) * exec_qty
                
            position["realizedPnl"] += trade_pnl
            position["currentQty"] = max(0, prev_qty - exec_qty)
            position["investedAmount"] = position["currentQty"] * prev_avg
            
            # Si cantidad llega a 0, cerramos
            if position["currentQty"] <= 0.0000001:
                position["status"] = "CLOSED"
                position["closedAt"] = datetime.utcnow()

        # 3. Calcular ROI actual
        if position["avgEntryPrice"] > 0:
            current_val = position["currentQty"] * exec_price
            cost_val = position["currentQty"] * position["avgEntryPrice"]
            
            unrealized_pnl = 0
            if position["side"] == "BUY":
                unrealized_pnl = current_val - cost_val
                position["roi"] = ((exec_price - position["avgEntryPrice"]) / position["avgEntryPrice"]) * 100
            else:
                unrealized_pnl = cost_val - current_val
                position["roi"] = ((position["avgEntryPrice"] - exec_price) / position["avgEntryPrice"]) * 100
            
            position["unrealizedPnl"] = unrealized_pnl

        # 4. Guardar en BD (Upsert)
        position["updatedAt"] = datetime.utcnow()
        
        if "_id" in position:
            await positions_coll.replace_one({"_id": position["_id"]}, position)
            return position["currentQty"], position["avgEntryPrice"], position["roi"]
        else:
            await positions_coll.insert_one(position)
            return position["currentQty"], position["avgEntryPrice"], 0.0

    async def _execute_simulated(self, bot, action, side, price, amount):
        """Ejecuta simulación actualizando DB y la colección 'positions'."""
        qty_executed = amount / price
        
        # Llamar al nuevo gestor de posiciones
        final_qty, final_avg_price, current_roi = await self._update_simulation_position_db(
            bot_instance=bot,
            action=action,
            side=side,
            exec_price=price,
            exec_qty=qty_executed,
            exec_amount=amount
        )

        pnl = 0 
        if action == "FLIP":
             pnl = self._calculate_pnl(bot, price)

        # Actualizar bot_instances (para compatibilidad)
        await self._update_bot_db(bot['_id'], bot.get('side', side), final_qty, final_avg_price, pnl)

        self.logger.info(f"📈 SIM EXEC: {bot['symbol']} | Side: {side} | Qty: {qty_executed:.4f} | Avg: {final_avg_price:.2f} | ROI: {current_roi:.2f}% | PnL: {pnl:.2f}")

        return {
            "success": True,
            "status": "executed",
            "price": price,
            "amount": amount,
            "side": side,
            "pnl": pnl,
            "new_position_avg": final_avg_price,
            "roi": current_roi
        }

    async def _execute_real(self, bot, action, side, price, amount):
        """Ejecuta operaciones reales usando create_order."""
        user_id = str(bot.get('user_id'))
        exchange_id = bot.get('exchangeId') or bot.get('exchange_id', 'binance')
        symbol = bot['symbol']

        realized_pnl = 0

        # 1. Si es FLIP, primero CERRAR la posición existente
        if action == "FLIP":
            close_side = "SELL" if bot.get('side') == "BUY" else "BUY"
            current_qty = float(bot.get('position', {}).get('qty', 0))

            if current_qty > 0:
                self.logger.info(f"🔄 REAL FLIP: Closing {current_qty} {symbol} ({close_side})")
                close_res_dict = await self.real_exchange.execute_trade(
                    symbol=symbol,
                    side=close_side,
                    amount=current_qty,
                    user_id=user_id,
                    exchange_id=exchange_id
                )

                if not close_res_dict.get("success"):
                    return {"success": False, "reason": f"Flip Close Failed: {close_res_dict.get('message')}"}
                
                close_order = close_res_dict.get("details", {})
                # Calcular PnL Real
                close_price = close_order.get('average') or close_order.get('price') or price
                realized_pnl = self._calculate_realized_pnl_value(bot, close_price)

        # 2. Abrir la nueva posición (o DCA)
        # Nota: CCXT Spot amount suele ser en base currency (BTC).
        # Si amount es USDT, calculamos estimado.
        qty_to_buy = amount / price

        # Params para quote order qty si es soportado (Binance)
        params = {}
        # if side == "BUY": params = {"cost": amount} # Optional optimization

        open_res_dict = await self.real_exchange.execute_trade(
            symbol=symbol,
            side=side,
            amount=qty_to_buy,
            user_id=user_id,
            exchange_id=exchange_id
        )

        if not open_res_dict.get("success"):
             return {"success": False, "reason": f"Open Failed: {open_res_dict.get('message')}"}

        # 3. Calcular nuevos valores para DB
        open_order = open_res_dict.get("details", {})
        final_price = open_order.get('average') or open_order.get('price') or price
        final_qty = open_order.get('amount') or qty_to_buy
        order_id = open_res_dict.get("order_id")
        
        if action == "DCA":
            curr_pos = bot.get('position', {})
            curr_q = float(curr_pos.get('qty', 0))
            curr_avg = float(curr_pos.get('avg_price', 0))
            
            total_cost = (curr_q * curr_avg) + (final_qty * final_price)
            final_qty += curr_q
            final_price = total_cost / final_qty if final_qty > 0 else final_price

        # Actualizar DB
        await self._update_bot_db(bot['_id'], side, final_qty, final_price, realized_pnl)

        return {
            "success": True,
            "status": "executed",
            "price": final_price,
            "side": side,
            "order_id": order_id,
            "pnl": realized_pnl
        }

    async def _update_bot_db(self, bot_id, side, qty, price, pnl):
        await self.db.db["bot_instances"].update_one(
            {"_id": ObjectId(bot_id)},
            {
                "$set": {
                    "side": side,
                    "position": {"qty": float(qty), "avg_price": float(price)},
                    "last_execution": datetime.utcnow()
                },
                "$inc": {"total_pnl": float(pnl)}
            }
        )

    def _calculate_realized_pnl_value(self, bot, exit_price):
        """Calcula PnL realizado en valor monetario (USDT)."""
        pos = bot.get('position', {})
        qty = float(pos.get('qty', 0))
        avg = float(pos.get('avg_price', 0))
        side = bot.get('side')

        if qty == 0 or avg == 0: return 0.0

        if side == "BUY":
            return (exit_price - avg) * qty
        else:
            return (avg - exit_price) * qty

    async def _persist_operation(self, bot_instance, signal_data, exec_result):
        """Guarda la señal y el trade en MongoDB."""
        trade_doc = {
            "userId": bot_instance.get('user_id'),
            "botId": str(bot_instance.get('id') or bot_instance.get('_id')),
            "symbol": bot_instance.get('symbol'),
            "side": exec_result.get('side').upper(),
            "price": exec_result.get('price'),
            "amount": exec_result.get('amount'),
            "pnl": exec_result.get('pnl', 0),
            "mode": bot_instance.get('mode'),
            "marketType": bot_instance.get('market_type'),
            "timestamp": datetime.utcnow()
        }
        await self.db.db["trades"].insert_one(trade_doc)

        # También emitir por socket
        if self.socket:
            await self.socket.emit_to_user(str(bot_instance.get('user_id')), "operation_update", trade_doc)

        # --- TASK 6.3: NOTIFICACIONES TELEGRAM ---
        # Call Telegram Adapter to send alert
        if exec_result and exec_result.get('status') in ['executed', 'closed']:
            try:
                # Lazy import to avoid circular dep
                from api.src.adapters.driven.notifications.telegram_adapter import TelegramAdapter
                from api.src.infrastructure.telegram.telegram_bot_manager import bot_manager
                
                # Resolve User ID
                user_id_obj = bot_instance.get('user_id')
                user_id = str(user_id_obj) if user_id_obj else None
                
                # Get active bot for user
                user_bot = bot_manager.get_user_bot(user_id) if user_id else None
                
                if user_bot:
                    tg_adapter = TelegramAdapter(bot=user_bot, user_id=user_id)
                    
                    # Prepare data for alert
                    alert_data = {
                        "symbol": bot_instance.get('symbol'),
                        "side": exec_result.get('side', 'unknown'),
                        "price": exec_result.get('price', 0),
                        "amount": exec_result.get('amount', 0),
                        "pnl": exec_result.get('pnl', 0),
                        "is_simulated": exec_result.get('is_simulated', False),
                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    }
                    
                    # Send (Fire & Forget)
                    asyncio.create_task(tg_adapter.send_trade_alert(alert_data))
            except Exception as e:
                self.logger.error(f"Error sending Telegram alert: {e}")

        # --- TAREA 4.3: NOTIFICACIÓN EN TIEMPO REAL (Socket) ---
        if self.socket and exec_result and exec_result.get('status') == 'executed':
            event_payload = {
                "bot_id": str(bot_instance.get('_id', 'unknown')), 
                "symbol": bot_instance.get('symbol'),
                "type": "LONG" if signal_data.get('signal') == BaseStrategy.SIGNAL_BUY else "SHORT",
                "price": exec_result.get('price', signal_data.get('price')),
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "createdAt": datetime.utcnow().isoformat() + "Z",
                "mode": bot_instance.get('mode'),
                "pnl_impact": exec_result.get('pnl', 0),
                "exchange_id": bot_instance.get("exchangeId", "binance") # Added for Task 3.2
            }
            # Emitimos el evento que el monitor híbrido en React capturará
            await self.socket.emit_to_user(str(bot_instance.get('user_id')), "live_execution_signal", event_payload)
            
        return exec_result or {"status": "executed", "details": exec_result}

    async def _apply_profit_guard(self, bot_instance, signal, current_price):
        """
        Bloquea cambios de posición si el PnL actual es negativo,
        evitando realizar pérdidas en estrategias de tendencia.
        """
        pos = bot_instance.get('position', {'qty': 0, 'avg_price': 0})
        current_side = bot_instance.get('side')
        target_side = "BUY" if signal == BaseStrategy.SIGNAL_BUY else "SELL"

        # 1. Si no hay posición, permitimos entrada
        if not current_side or pos.get('qty', 0) == 0:
            return True

        # 2. Si es DCA (mismo lado), permitimos
        if current_side == target_side:
            return True

        # 3. Si es FLIP (lado opuesto), verificamos PnL
        pnl = self._calculate_pnl(bot_instance, current_price)
        
        # Permitimos cerrar si el PnL > -0.1% (pequeño margen de break-even)
        if pnl < -0.1:
            self.logger.warning(f"🛡️ Profit Guard: Bloqueado FLIP de {current_side} a {target_side} para {bot_instance['symbol']}. PnL actual: {pnl:.2f}%")
            return False

        return True

    async def _check_risk_and_balance(self, bot_instance, amount, current_price):
        """
        Sprint 3: Valida saldo disponible y riesgo antes de operar.
        """
        mode = bot_instance.get('mode', 'simulated')
        symbol = bot_instance['symbol']
        user_id = bot_instance.get('user_id')
        
        if mode == 'simulated':
            # En simulación, asumimos saldo infinito o trackeamos 'virtualBalances' en AppConfig
            # Por simplicidad en Sprint 3, permitimos siempre en Sim
            return True
            
        # Real Checks
        try:
            # Check Balance
            # Assuming symbol like "BTC/USDT", quote is USDT
            quote_currency = symbol.split('/')[1]
            exchange_id = bot_instance.get("exchangeId") or bot_instance.get("exchange_id")
            
            # FIX: Use fetch_balance consistent with IExchangePort
            balances = await self.real_exchange.fetch_balance(str(user_id), exchange_id=exchange_id)

            # Find quote balance in List[Balance]
            balance_obj = next((b for b in balances if b.asset == quote_currency), None)
            available = balance_obj.free if balance_obj else 0.0
            
            if available < amount:
                self.logger.warning(f"❌ Insufficient Funds for {symbol}: Need {amount} {quote_currency}, Have {available}")
                return False
                
            return True
        except Exception as e:
            self.logger.error(f"Error checking balance: {e}")
            return False # Fail safe

    def _calculate_pnl(self, bot_instance, current_price):
        """Calcula PnL no realizado % basado en la posición actual."""
        pos = bot_instance.get('position', {})
        qty = pos.get('qty', 0)
        avg_price = pos.get('avg_price', 0)
        side = bot_instance.get('side')
        
        if qty == 0 or avg_price == 0:
            return 0.0
            
        if side == 'BUY':
            return ((current_price - avg_price) / avg_price) * 100
        elif side == 'SELL':
            return ((avg_price - current_price) / avg_price) * 100
        return 0.0
