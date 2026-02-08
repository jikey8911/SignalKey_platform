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
        Procesa una señal entrante. Soporta Long/Short y Flipping de posiciones.
        Lanza eventos de socket para el monitor híbrido en cada operación.
        """
        if bot_instance.get('status') != 'active':
            return None

        mode = bot_instance.get('mode', 'simulated')
        symbol = bot_instance['symbol']
        signal = signal_data['signal'] # 1: Buy (Long), 2: Sell (Short)
        price = signal_data['price']
        is_alert = signal_data.get('is_alert', False) # Flag para ignorar Profit Guard

        # 1. Obtener monto de inversión (Tarea 3.3 - Refactor Sprint 3)
        # Prioridad 1: Monto configurado en el Bot (Validado por Schema)
        # Prioridad 2: Límite global (Safety net)
        
        amount = bot_instance.get('amount', 10.0) 
        
        # Check Global Limits (Safety Net)
        config = await self.db.db["app_configs"].find_one({"userId": bot_instance.get('user_id')})
        global_limit = 1000.0 # High default
        if config and 'investmentLimits' in config:
             if bot_instance.get('market_type') in ['spot', 'cex']:
                 global_limit = config['investmentLimits'].get('cexMaxAmount', 100.0)
             else:
                 global_limit = config['investmentLimits'].get('dexMaxAmount', 50.0)

        # Enforce Hard Limit
        if amount > global_limit:
            self.logger.warning(f"⚠️ Bot amount {amount} exceeds global limit {global_limit}. Capping.")
            amount = global_limit

        # 2. Risk & Balance Check
        if not await self._check_risk_and_balance(bot_instance, amount, price):
             return {"status": "blocked", "reason": "insufficient_balance_or_risk"}

        # 3. Preparar datos de la posición actual
        current_pos = bot_instance.get('position', {'qty': 0, 'avg_price': 0})
        current_side = bot_instance.get('side') # "BUY" (Long) o "SELL" (Short)
        unrealized_pnl_pct = self._calculate_pnl(bot_instance, price)

        # --- PROFIT GUARD ---
        # No cerrar pnl negativo al menos que sea alerta
        if not is_alert and not await self._apply_profit_guard(bot_instance, signal, price):
            self.logger.info(f"🛡️ Profit Guard bloqueó señal {signal} para {symbol} (PnL: {unrealized_pnl_pct:.2f}%)")
            return {"status": "blocked", "reason": "profit_guard"}

        execution_result = None

        # 2. Lógica de Inversión / Flip
        # Si la señal pide cambiar de dirección, ejecutamos un flip atómico.
        target_side = "BUY" if signal == BaseStrategy.SIGNAL_BUY else "SELL"
        is_flip = current_side and current_side != target_side and current_pos.get('qty', 0) > 0

        if mode == 'simulated':
            # Simulación: El SimulationService actualiza la posición internamente.
            # Lo extendemos para soportar Shorts y Flips.
            execution_result = await self._execute_simulated_trade(bot_instance, signal, price, amount, is_flip)
        else:
            # Ejecución Real vía CCXT
            execution_result = await self._execute_real_trade(bot_instance, signal, price, amount, is_flip)

        # 3. Persistencia de la señal y la operación
        await self._persist_signal(bot_instance, signal_data)

        if execution_result and execution_result.get('status') == 'executed':
            await self._persist_operation(bot_instance, signal_data, execution_result)

        return execution_result

    async def _persist_signal(self, bot_instance, signal_data):
        """Persiste la señal técnica recibida."""
        try:
            from api.src.domain.entities.signal import Signal, SignalStatus, Decision
            from api.src.adapters.driven.persistence.mongodb_signal_repository import MongoDBSignalRepository
            signal_repo = MongoDBSignalRepository(self.db)
            
            new_sig = Signal(
                id=None,
                userId=str(bot_instance.get('user_id')),
                source="AUTO_STRATEGY",
                rawText=f"Signal {signal_data['signal']} at {signal_data['price']}",
                status=SignalStatus.EXECUTING,
                createdAt=datetime.utcnow(),
                symbol=bot_instance['symbol'],
                decision=Decision.BUY if signal_data['signal'] == 1 else Decision.SELL,
                botId=str(bot_instance.get('id') or bot_instance.get('_id'))
            )
            await signal_repo.save(new_sig)
        except Exception as e:
            self.logger.error(f"Error persistiendo señal: {e}")

    async def _execute_simulated_trade(self, bot_instance, signal, price, amount, is_flip):
        """Ejecuta un trade simulado con soporte para flipping."""
        bot_id = str(bot_instance.get('id') or bot_instance.get('_id'))
        side = "buy" if signal == BaseStrategy.SIGNAL_BUY else "sell"
        target_side = side.upper()

        current_pos = bot_instance.get('position', {'qty': 0, 'avg_price': 0})
        current_side = bot_instance.get('side')

        # Si es flip, calculamos el PnL de cierre
        closed_pnl = 0
        if is_flip:
             closed_pnl = self._calculate_pnl(bot_instance, price)
             self.logger.info(f"🔄 SIM FLIP: Cerrando {current_side} con PnL: {closed_pnl:.2f}%")

        # Calculamos nueva posición
        # En flip, el monto total es Amount (para la nueva dirección)
        # Ignoramos la qty anterior porque se "cierra" virtualmente
        new_qty = amount / price
        updated_pos = {'qty': new_qty, 'avg_price': price}

        trade_log = {
            "bot_id": bot_id,
            "symbol": bot_instance['symbol'],
            "side": side,
            "price": price,
            "amount": amount,
            "timestamp": datetime.now(),
            "mode": "simulated",
            "is_flip": is_flip,
            "closed_pnl": closed_pnl
        }

        # Actualizar bot en DB
        await self.db.db["bot_instances"].update_one(
            {"_id": ObjectId(bot_id)},
            {"$set": {
                "position": updated_pos,
                "side": target_side,
                "last_execution": datetime.now()
            }}
        )

        return {"status": "executed", **trade_log}

    async def _execute_real_trade(self, bot_instance, signal, price, amount, is_flip):
        """Ejecuta un trade real vía CCXT corrigiendo cálculo de unidades."""
        symbol = bot_instance['symbol']
        side = 'buy' if signal == BaseStrategy.SIGNAL_BUY else 'sell'
        target_side = side.upper()

        from api.src.domain.entities.signal import SignalAnalysis, Decision, MarketType, TradingParameters

        # 1. Calcular cuántas monedas queremos comprar/vender con el dinero (USDT)
        # target_qty_base: Cantidad del activo base equivalente a la inversión deseada
        # amount es en USDT (e.g. 50.0), price es el precio actual (e.g. 50000.0)
        target_qty_base = amount / price 

        # 2. Calcular tamaño total de la orden (Order Size)
        current_qty = bot_instance.get('position', {}).get('qty', 0.0)
        
        exec_qty = target_qty_base
        
        if is_flip:
            # Si es FLIP, necesitamos cerrar lo anterior + abrir lo nuevo.
            market_type = bot_instance.get('market_type', 'spot').upper()
            
            if market_type == 'FUTURES':
                # En Futuros, para flipear Long->Short o viceversa con una sola orden,
                # necesitamos vender (qty_actual + qty_nueva).
                exec_qty = target_qty_base + current_qty
            else:
                # SPOT: No existe flip atómico de posición negativa.
                # Si la señal es SELL (Flip Long->Short): Vendemos TODO lo que tenemos.
                # Spot no permite abrir Short real con este motor simple.
                if side == 'sell':
                    exec_qty = current_qty # Vender toda la tenencia
                else:
                    exec_qty = target_qty_base # Compra normal (inversión nueva)

        # Validar precisión mínima (simple 6 decimales para crypto)
        exec_qty = float(f"{exec_qty:.6f}")
        if exec_qty <= 0:
             self.logger.warning(f"Trade skipped: Calculated qty is zero or negative ({exec_qty}) for {symbol}")
             return {"status": "skipped", "reason": "qty_zero"}

        analysis = SignalAnalysis(
            symbol=symbol,
            decision=Decision.BUY if side == 'buy' else Decision.SELL,
            market_type=bot_instance.get('market_type', 'spot').upper(),
            confidence=0.9,
            reasoning=f"Automated Bot {'Flip' if is_flip else 'Signal'}: {bot_instance.get('strategy_name')}",
            parameters=TradingParameters(amount=exec_qty)
        )

        user_id = str(bot_instance.get('user_id', "default_user"))

        try:
            exchange_id = bot_instance.get("exchangeId") or bot_instance.get("exchange_id")
            trade_result = await self.real_exchange.execute_trade(analysis, user_id, exchange_id=exchange_id)
            if trade_result.success:
                # Actualizar posición local
                updated_pos = {'qty': amount / price, 'avg_price': trade_result.price or price}
                bot_id = str(bot_instance.get('id') or bot_instance.get('_id'))
                await self.db.db["bot_instances"].update_one(
                    {"_id": ObjectId(bot_id)},
                    {"$set": {
                        "position": updated_pos,
                        "side": target_side,
                        "last_execution": datetime.now()
                    }}
                )
                return {
                    "status": "executed",
                    "price": trade_result.price or price,
                    "amount": amount,
                    "side": side,
                    "order_id": trade_result.order_id
                }
            else:
                return {"status": "failed", "reason": trade_result.error}
        except Exception as e:
            self.logger.error(f"Error en ejecución real: {e}")
            return {"status": "error", "reason": str(e)}

    async def _persist_operation(self, bot_instance, signal_data, exec_result):
        """Guarda la señal y el trade en MongoDB."""
        trade_doc = {
            "userId": bot_instance.get('user_id'),
            "botId": str(bot_instance.get('id') or bot_instance.get('_id')),
            "symbol": bot_instance.get('symbol'),
            "side": exec_result.get('side').upper(),
            "price": exec_result.get('price'),
            "amount": exec_result.get('amount'),
            "pnl": exec_result.get('closed_pnl', 0),
            "mode": bot_instance.get('mode'),
            "marketType": bot_instance.get('market_type'),
            "timestamp": datetime.now()
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
                "timestamp": datetime.now().isoformat(),
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
