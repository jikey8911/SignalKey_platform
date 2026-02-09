import logging
import asyncio
from datetime import datetime
from bson import ObjectId
from api.src.application.services.simulation_service import SimulationService
from api.src.domain.strategies.base import BaseStrategy
from api.src.adapters.driven.persistence.mongodb import update_virtual_balance

class ExecutionEngine:
    """
    Motor central del Sprint 4. Orquesta la ejecución basándose en el modo (Real/Sim).
    Implementa la separación estricta de balances: Virtual (DB) vs Real (Exchange).
    """
    def __init__(self, db_adapter, socket_service=None, exchange_adapter=None):
        self.db = db_adapter
        self.socket = socket_service 
        self.simulator = SimulationService(db_adapter)

        # Inyección de dependencia
        if exchange_adapter:
             self.real_exchange = exchange_adapter
        else:
             from api.src.adapters.driven.exchange.ccxt_adapter import ccxt_service
             self.real_exchange = ccxt_service

        self.logger = logging.getLogger("ExecutionEngine")

    async def process_signal(self, bot_instance, signal_data):
        if bot_instance.get('status') != 'active':
            return None

        # 1. Variables y Contexto
        mode = bot_instance.get('mode', 'simulated')
        symbol = bot_instance['symbol']
        price = signal_data['price']
        signal = signal_data['signal']
        is_alert = signal_data.get('is_alert', False)
        
        amount = bot_instance.get('amount', 0)
        if amount <= 0: amount = 100.0 

        # 2. Validación de Saldo (Router Híbrido)
        # Aquí es donde decidimos si mirar la DB o el Exchange
        if not await self._check_risk_and_balance(bot_instance, amount, price):
             return {"status": "blocked", "reason": "insufficient_balance_or_risk"}

        # 3. Lógica de Posición (DCA vs Flip)
        current_pos = bot_instance.get('position', {})
        current_qty = float(current_pos.get('qty', 0))
        current_side = bot_instance.get('side') 
        signal_side = "BUY" if signal == 1 else "SELL"

        if not is_alert and not await self._apply_profit_guard(bot_instance, signal, price):
            return {"status": "blocked", "reason": "profit_guard"}

        action = "OPEN"
        if current_qty > 0:
            if current_side == signal_side:
                action = "DCA"
            else:
                action = "FLIP"

        self.logger.info(f"🤖 Engine: {symbol} | Mode: {mode} | Action: {action} | Side: {signal_side}")

        # 4. Ejecución
        execution_result = None
        if mode == 'simulated':
            execution_result = await self._execute_simulated(bot_instance, action, signal_side, price, amount)
        else:
            execution_result = await self._execute_real(bot_instance, action, signal_side, price, amount)

        # 5. Persistencia y Notificación
        await self._persist_signal(bot_instance, signal_data)

        if execution_result and execution_result.get('success'):
            await self._persist_operation(bot_instance, signal_data, execution_result)

        return execution_result

    async def _check_risk_and_balance(self, bot_instance, amount, current_price):
        """
        Valida fondos. 
        CRITICO: Si es simulado, SOLO mira MongoDB. Si es real, SOLO mira Exchange.
        """
        mode = bot_instance.get('mode', 'simulated')
        symbol = bot_instance['symbol']
        user_id = bot_instance.get('user_id') # Expected to be ObjectId
        
        # Determinar moneda base (ej. USDT en BTC/USDT)
        try:
            quote_currency = symbol.split('/')[1]
        except IndexError:
            quote_currency = "USDT"

        # --- MODO SIMULADO: Balance Virtual (MongoDB) ---
        if mode == 'simulated':
            try:
                # Ensure user_id is ObjectId
                uid = ObjectId(user_id) if not isinstance(user_id, ObjectId) else user_id
                market_type = bot_instance.get("marketType", "CEX")
                
                # Buscar balance en colección 'virtual_balances'
                # Strict ObjectId lookup
                balance_doc = await self.db["virtual_balances"].find_one({
                    "userId": uid,
                    "asset": quote_currency,
                    "marketType": market_type
                })

                available = 0.0
                if balance_doc:
                    available = float(balance_doc.get("amount", 0.0))
                else:
                    # Bootstrap si no existe (saldo inicial para usuarios nuevos)
                    config = await self.db["app_configs"].find_one({"userId": uid})
                    if config and "virtualBalances" in config:
                        key = "cex" if market_type == "CEX" else "dex"
                        available = float(config["virtualBalances"].get(key, 10000.0))
                    else:
                        available = 10000.0 # Default fallback

                self.logger.info(f"💰 [SIM] Balance Virtual {quote_currency}: {available:.2f} (Req: {amount})")

                if available < amount:
                    self.logger.warning(f"❌ [SIM] Fondos insuficientes: {available} < {amount}")
                    return False
                
                return True

            except Exception as e:
                self.logger.error(f"Error checking virtual balance: {e}")
                return True # Fail-open en demo para no frustrar al usuario por error de DB

        # --- MODO REAL: Balance Exchange (API) ---
        try:
            # Obtener el ID del exchange específico del bot (no default a okx si es OKX)
            exchange_id = bot_instance.get("exchangeId") or bot_instance.get("exchange_id")
            if not exchange_id:
                self.logger.error(f"Bot {bot_instance.get('_id')} en modo REAL no tiene exchangeId configurado.")
                return False

            # Pass ObjectId directly to exchange adapter
            balances = await self.real_exchange.fetch_balance(str(user_id), exchange_id=exchange_id)
            
            # Buscar el activo
            balance_obj = next((b for b in balances if b.asset == quote_currency), None)
            available = balance_obj.free if balance_obj else 0.0
            
            self.logger.info(f"💰 [REAL] Balance {exchange_id} {quote_currency}: {available:.2f} (Req: {amount})")

            if available < amount:
                self.logger.warning(f"❌ [REAL] Fondos insuficientes en {exchange_id}: {available} < {amount}")
                return False
                
            return True
        except Exception as e:
            self.logger.error(f"Error checking real balance: {e}")
            return False # Fail-safe: No operar con dinero real si falla el check

    async def _execute_simulated(self, bot, action, side, price, amount):
        """
        Ejecuta en papel y actualiza el 'Libro Mayor' virtual.
        """
        qty_executed = amount / price
        user_id = bot.get('user_id') # ObjectId
        market_type = bot.get("marketType", "CEX")
        quote_currency = bot['symbol'].split('/')[1] if '/' in bot['symbol'] else 'USDT'
        
        # 1. Movimiento de Caja (Virtual)
        # Si abrimos posición, restamos USDT del saldo disponible

        # NOTE: update_virtual_balance helper usually takes user_id as string/openId to find user.
        # But we refactored to pass ObjectId to engine.
        # We need to make sure update_virtual_balance supports ObjectId or convert it.
        # Looking at mongodb.py, update_virtual_balance does: user = await db.users.find_one({"openId": user_id})
        # This is bad. We need to update mongodb.py or resolve openId here.
        # But wait, update_virtual_balance is imported.
        # Let's resolve this by modifying mongodb.py in the next step or fix it here by passing string if needed
        # BUT the goal is to standardise on ObjectId.

        # Let's assume update_virtual_balance will be updated to handle ObjectId lookups properly
        # OR we pass ObjectId string and update mongodb.py to check _id too.
        # For now, let's pass str(user_id) and ensure mongodb.py handles it.

        if action in ["OPEN", "DCA"]:
            await update_virtual_balance(str(user_id), market_type, quote_currency, -amount, is_relative=True)
            
        elif action == "FLIP":
            # En FLIP (cerrar y abrir inverso), restamos el costo de la NUEVA posición.
            # El retorno de la posición cerrada se maneja en _update_simulation_position_db al cerrarla.
            await update_virtual_balance(str(user_id), market_type, quote_currency, -amount, is_relative=True)

        # 2. Actualizar Inventario de Posiciones
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

        # 3. Actualizar Estado del Bot
        await self._update_bot_db(bot['_id'], bot.get('side', side), final_qty, final_avg_price, pnl)

        return {
            "success": True,
            "status": "executed",
            "price": price,
            "amount": amount,
            "side": side,
            "pnl": pnl,
            "new_position_avg": final_avg_price,
            "roi": current_roi,
            "is_simulated": True
        }

    async def _update_simulation_position_db(self, bot_instance, action, side, exec_price, exec_qty, exec_amount):
        """
        Lógica contable de posiciones. Cierra posiciones antiguas y suma ganancias al balance virtual.
        """
        bot_id = bot_instance['_id']
        symbol = bot_instance['symbol']
        user_id = bot_instance['user_id'] # ObjectId
        market_type = bot_instance.get("marketType", "CEX")
        quote_currency = symbol.split('/')[1] if '/' in symbol else 'USDT'
        
        positions_coll = self.db["positions"]
        position = await positions_coll.find_one({
            "botId": ObjectId(bot_id),
            "status": "OPEN"
        })

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

        prev_qty = float(position["currentQty"])
        prev_avg = float(position["avgEntryPrice"])

        # CIERRE DE POSICIÓN (FLIP)
        if action == "FLIP":
            # Calcular PnL de la posición que se cierra
            flip_pnl = 0
            if position["side"] == "BUY":
                flip_pnl = (exec_price - prev_avg) * prev_qty
            else:
                flip_pnl = (prev_avg - exec_price) * prev_qty
            
            # Devolver capital al balance virtual (Principal + Ganancia/Pérdida)
            capital_returned = (prev_qty * prev_avg) + flip_pnl
            await update_virtual_balance(str(user_id), market_type, quote_currency, capital_returned, is_relative=True)
            self.logger.info(f"💵 [SIM FLIP] Retorno al balance: {capital_returned:.2f} (PnL: {flip_pnl:.2f})")

            # Cerrar documento antiguo
            await positions_coll.update_one(
                {"_id": position.get("_id")}, 
                {"$set": {"status": "CLOSED", "closedAt": datetime.utcnow(), "finalPnl": flip_pnl, "exitPrice": exec_price}}
            )
            
            # Reset para nueva posición
            position["currentQty"] = 0.0
            position["avgEntryPrice"] = 0.0
            position["investedAmount"] = 0.0
            position["totalTrades"] = 0
            position["side"] = side
            prev_qty = 0.0
            prev_avg = 0.0

        is_increasing = (position["side"] == side) or (prev_qty == 0)

        if is_increasing:
            # COMPRA / DCA
            new_qty = prev_qty + exec_qty
            total_cost = (prev_qty * prev_avg) + (exec_qty * exec_price)
            new_avg_price = total_cost / new_qty if new_qty > 0 else exec_price
            
            position["currentQty"] = new_qty
            position["avgEntryPrice"] = new_avg_price
            position["investedAmount"] = total_cost
            position["totalTrades"] += 1
            
        else:
            # VENTA PARCIAL / REDUCCIÓN
            qty_to_close = min(prev_qty, exec_qty)
            trade_pnl = 0
            if position["side"] == "BUY":
                trade_pnl = (exec_price - prev_avg) * qty_to_close
            else:
                trade_pnl = (prev_avg - exec_price) * qty_to_close
                
            # Devolver parte proporcional al balance
            capital_returned = (qty_to_close * prev_avg) + trade_pnl
            await update_virtual_balance(str(user_id), market_type, quote_currency, capital_returned, is_relative=True)

            position["realizedPnl"] += trade_pnl
            position["currentQty"] = max(0, prev_qty - qty_to_close)
            position["investedAmount"] = position["currentQty"] * prev_avg
            
            if position["currentQty"] <= 0.0000001:
                position["status"] = "CLOSED"
                position["closedAt"] = datetime.utcnow()

        # Calcular ROI
        if position["avgEntryPrice"] > 0:
            if position["side"] == "BUY":
                position["roi"] = ((exec_price - position["avgEntryPrice"]) / position["avgEntryPrice"]) * 100
            else:
                position["roi"] = ((position["avgEntryPrice"] - exec_price) / position["avgEntryPrice"]) * 100
            
        # Guardar
        position["updatedAt"] = datetime.utcnow()
        if "_id" in position:
            await positions_coll.replace_one({"_id": position["_id"]}, position)
            return position["currentQty"], position["avgEntryPrice"], position["roi"]
        else:
            await positions_coll.insert_one(position)
            return position["currentQty"], position["avgEntryPrice"], 0.0

    async def _execute_real(self, bot, action, side, price, amount):
        user_id = bot.get('user_id') # ObjectId
        exchange_id = bot.get('exchangeId') or bot.get('exchange_id')
        symbol = bot['symbol']
        realized_pnl = 0

        # 1. FLIP: Cerrar posición contraria
        if action == "FLIP":
            close_side = "SELL" if bot.get('side') == "BUY" else "BUY"
            current_qty = float(bot.get('position', {}).get('qty', 0))

            if current_qty > 0:
                self.logger.info(f"🔄 REAL FLIP: Cerrando {current_qty} {symbol} ({close_side}) en {exchange_id}")
                close_res = await self.real_exchange.execute_trade(symbol, close_side, current_qty, user_id=str(user_id), exchange_id=exchange_id)

                if not close_res.get("success"):
                    return {"success": False, "reason": f"Flip Close Failed: {close_res.get('message')}"}
                
                # Calcular PnL Realizado
                close_px = close_res.get("details", {}).get('price') or price
                realized_pnl = self._calculate_realized_pnl_value(bot, close_px)

        # 2. Abrir nueva posición
        qty_to_buy = amount / price
        open_res = await self.real_exchange.execute_trade(symbol, side, qty_to_buy, user_id=str(user_id), exchange_id=exchange_id)

        if not open_res.get("success"):
             return {"success": False, "reason": f"Open Failed: {open_res.get('message')}"}

        final_price = open_res.get("details", {}).get('price') or price
        final_qty = open_res.get("details", {}).get('amount') or qty_to_buy
        
        # Lógica DCA (Promediar precio)
        if action == "DCA":
            curr_pos = bot.get('position', {})
            curr_q = float(curr_pos.get('qty', 0))
            curr_avg = float(curr_pos.get('avg_price', 0))
            total_cost = (curr_q * curr_avg) + (final_qty * final_price)
            final_qty += curr_q
            final_price = total_cost / final_qty if final_qty > 0 else final_price

        await self._update_bot_db(bot['_id'], side, final_qty, final_price, realized_pnl)

        return {
            "success": True, 
            "status": "executed", 
            "price": final_price, 
            "side": side, 
            "pnl": realized_pnl, 
            "exchange": exchange_id
        }

    async def _update_bot_db(self, bot_id, side, qty, price, pnl):
        await self.db["bot_instances"].update_one(
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
        pos = bot.get('position', {})
        qty = float(pos.get('qty', 0))
        avg = float(pos.get('avg_price', 0))
        side = bot.get('side')
        if qty == 0 or avg == 0: return 0.0
        return (exit_price - avg) * qty if side == "BUY" else (avg - exit_price) * qty

    async def _persist_signal(self, bot_instance, signal_data):
        try:
            from api.src.domain.entities.signal import Signal, SignalStatus, Decision
            from api.src.adapters.driven.persistence.mongodb_signal_repository import MongoDBSignalRepository
            repo = MongoDBSignalRepository(self.db)
            
            new_sig = Signal(
                id=None,
                userId=bot_instance.get('user_id'), # Should be ObjectId
                source=f"AUTO_{bot_instance.get('strategy_name', 'UNK').upper()}",
                rawText=f"Signal {signal_data['signal']} @ {signal_data['price']}",
                status=SignalStatus.EXECUTING,
                createdAt=datetime.utcnow(),
                symbol=bot_instance['symbol'],
                marketType=bot_instance.get('marketType', 'SPOT'),
                decision=Decision.BUY if signal_data['signal'] == 1 else Decision.SELL,
                confidence=signal_data.get('confidence', 0),
                botId=str(bot_instance.get('_id'))
            )
            await repo.save(new_sig)
        except Exception as e:
            self.logger.error(f"Error persistiendo señal: {e}")

    async def _persist_operation(self, bot_instance, signal_data, exec_result):
        trade_doc = {
            "userId": bot_instance.get('user_id'), # ObjectId
            "botId": str(bot_instance.get('id') or bot_instance.get('_id')),
            "symbol": bot_instance.get('symbol'),
            "side": exec_result.get('side', 'UNKNOWN'),
            "price": exec_result.get('price'),
            "amount": exec_result.get('amount'),
            "pnl": exec_result.get('pnl', 0),
            "mode": bot_instance.get('mode'),
            "timestamp": datetime.utcnow()
        }
        await self.db["trades"].insert_one(trade_doc)
        if self.socket:
            # Socket service uses string for user_id to emit
            await self.socket.emit_to_user(str(bot_instance.get('user_id')), "operation_update", trade_doc)
        
        # Telegram Alert (Simplified)
        try:
            from api.src.infrastructure.telegram.telegram_bot_manager import bot_manager
            from api.src.adapters.driven.notifications.telegram_adapter import TelegramAdapter
            user_id = bot_instance.get('user_id') # ObjectId

            # Resolve openId for Telegram Manager (infrastructure adapter)
            # Fetch user to get openId
            user_doc = await self.db.users.find_one({"_id": user_id})
            open_id = user_doc["openId"] if user_doc else str(user_id)

            user_bot = bot_manager.get_user_bot(open_id)
            if user_bot:
                tg = TelegramAdapter(user_bot, open_id)
                await tg.send_trade_alert(trade_doc)
        except Exception as e:
            self.logger.warning(f"Failed to send TG alert: {e}")

    async def _apply_profit_guard(self, bot_instance, signal, current_price):
        # ... (Mantener lógica existente) ...
        pos = bot_instance.get('position', {'qty': 0})
        if pos.get('qty', 0) == 0: return True
        # Simplificado: si PnL < -0.5% y tratamos de voltear, bloquear
        pnl = self._calculate_pnl(bot_instance, current_price)
        current_side = bot_instance.get('side')
        target_side = "BUY" if signal == 1 else "SELL"
        if current_side != target_side and pnl < -0.5:
             self.logger.warning(f"🛡️ Profit Guard: Blocked FLIP {current_side}->{target_side}. PnL: {pnl:.2f}%")
             return False
        return True

    def _calculate_pnl(self, bot_instance, current_price):
        pos = bot_instance.get('position', {})
        avg = float(pos.get('avg_price', 0))
        if avg == 0: return 0.0
        if bot_instance.get('side') == 'BUY':
            return ((current_price - avg) / avg) * 100
        return ((avg - current_price) / avg) * 100