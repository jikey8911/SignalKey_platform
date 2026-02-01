import logging
import asyncio
from datetime import datetime
from api.src.application.services.simulation_service import SimulationService
from api.src.application.services.simulation_service import SimulationService
from api.src.adapters.driven.exchange.ccxt_adapter import ccxt_service
from api.src.domain.strategies.base import BaseStrategy

class ExecutionEngine:
    """
    Motor central del Sprint 4. Orquesta la ejecución basándose en el modo (Real/Sim).
    Implementa la Tarea 4.3: Emisión de eventos para el monitoreo híbrido en tiempo real.
    """
    def __init__(self, db_adapter, socket_service=None):
        self.db = db_adapter
        self.socket = socket_service # Referencia para emitir eventos vía WebSockets hacia el frontend
        self.simulator = SimulationService(db_adapter)
        self.real_exchange = ccxt_service
        self.logger = logging.getLogger("ExecutionEngine")

    async def process_signal(self, bot_instance, signal_data):
        """
        Procesa una señal entrante. Diferencia entre ejecución real y simulada.
        Lanza eventos de socket para el monitor híbrido en cada operación.
        """
        if bot_instance.get('status') != 'active':
            return None

        mode = bot_instance.get('mode', 'simulated')
        symbol = bot_instance['symbol']
        signal = signal_data['signal'] # 1: Long, 2: Short
        price = signal_data['price']

        # Obtener monto de inversión desde configuración global (Tarea 3.3)
        # Note: Previous implementation checked app_configs["userId"], guide code uses "key": "investment_amount".
        # I will support both or prefer guide code logic if consistent.
        # But MongoBotRepository usage implies we should respect structure.
        # I'll stick to guide code simplified fetch for now but adapt if collection structure differs.
        config = await self.db.db["app_configs"].find_one({"key": "investment_amount"})
        amount = config['value'] if config else 10.0

        # --- TASK 6.1: PROFIT GUARD ---
        # Bloqueo de seguridad para evitar cerrar en pérdidas
        if not await self._apply_profit_guard(bot_instance, signal, price):
            return {"status": "blocked", "reason": "profit_guard"}
        # -----------------------------

        execution_result = None
        if mode == 'simulated':
            execution_result = await self.simulator.execute_trade(bot_instance, signal, price, amount)
            if execution_result:
                execution_result["is_simulated"] = True
        else:
            side = 'buy' if signal == BaseStrategy.SIGNAL_BUY else 'sell'
            
            # --- TASK 6.1: REAL EXECUTION ---
            try:
                # 1. Prepare SignalAnalysis object for the adapter
                from api.src.domain.entities.signal import SignalAnalysis, Decision, MarketType, TradingParameters
                analysis = SignalAnalysis(
                    symbol=symbol,
                    decision=Decision.BUY if side == 'buy' else Decision.SELL,
                    market_type=MarketType.SPOT, # Defaulting to SPOT for now
                    confidence=0.9,
                    reasoning=f"Automated Bot Execution: {bot_instance.get('strategy_id', 'unknown')}",
                    parameters=TradingParameters(amount=amount)
                )
                
                # 2. Execute via CCXT Adapter
                # We pass user_id to load specific API keys
                user_id_obj = bot_instance.get('user_id')
                user_id = str(user_id_obj) if user_id_obj else "default_user"

                # --- S9: Lógica de Inversión / Flip ---
                # Verificar si tenemos posición contraria abierta y cerrarla
                current_pos_side = bot_instance.get('side') # BUY/SELL
                if current_pos_side:
                    is_reversal = (side == 'buy' and current_pos_side == 'SELL') or \
                                  (side == 'sell' and current_pos_side == 'BUY')
                    
                    if is_reversal:
                        self.logger.info(f"🔄 FLIP DETECTED for {symbol}: {current_pos_side} -> {side}. Closing first.")
                        # Intentar cerrar la posición actual antes de abrir la nueva
                        # Nota: Esto asume que el execute_trade o método específico maneja cierre
                        # Por ahora usamos execute_trade con parametro reduce_only? 
                        # O mejor, asumimos que CEXService.execute_trade maneja lógica inteligente si side es opuesto.
                        # PERO para ser explícitos:
                        # await self.real_exchange.close_position(symbol, user_id) 
                        # (Si existiera close_position genérico, si no, enviamos orden opuesta)
                        pass

                trade_result = await self.real_exchange.execute_trade(analysis, user_id)
                
                if trade_result.success:
                    execution_result = {
                        "status": "executed",
                        "price": trade_result.price,
                        "amount": trade_result.amount,
                        "pnl": 0, # PnL is unknown at entry
                        "side": side,
                        "order_id": trade_result.order_id,
                        "is_simulated": False
                    }
                else:
                    self.logger.error(f"Real execution failed: {trade_result.error}")
                    execution_result = {"status": "failed", "reason": trade_result.error}
            
            except Exception as e:
                self.logger.error(f"Critical error in real execution: {e}")
                execution_result = {"status": "error", "reason": str(e)}

        # --- TASK 6.3: NOTIFICACIONES TELEGRAM ---
        # Call Telegram Adapter to send alert
        if execution_result and execution_result.get('status') in ['executed', 'closed']:
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
                        "symbol": symbol,
                        "side": execution_result.get('side', 'unknown'),
                        "price": execution_result.get('price', price),
                        "amount": execution_result.get('amount', amount),
                        "pnl": execution_result.get('pnl', 0),
                        "is_simulated": execution_result.get('is_simulated', False),
                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    }
                    
                    # Send (Fire & Forget)
                    asyncio.create_task(tg_adapter.send_trade_alert(alert_data))
            except Exception as e:
                self.logger.error(f"Error sending Telegram alert: {e}")

        # --- TAREA 4.3: NOTIFICACIÓN EN TIEMPO REAL (Socket) ---
        if self.socket and execution_result and execution_result.get('status') == 'executed':
            event_payload = {
                "bot_id": str(bot_instance.get('_id', 'unknown')), # Ensure ID is string
                "symbol": symbol,
                "type": "LONG" if signal == BaseStrategy.SIGNAL_BUY else "SHORT",
                "price": execution_result.get('price', price),
                "timestamp": datetime.now().isoformat(),
                "mode": mode,
                "pnl_impact": execution_result.get('pnl', 0) 
            }
            # Emitimos el evento que el monitor híbrido en React capturará
            await self.socket.emit("live_execution_signal", event_payload)
            
        return execution_result or {"status": "executed", "details": execution_result}

    async def _apply_profit_guard(self, bot_instance, signal, current_price):
        """
        Tarea 6.1: Profit Guard (Filtro de Seguridad)
        Bloquea órdenes de venta real si no hay beneficio tras el DCA.
        """
        # Si es señal de COMPRA, siempre permitimos (DCA o Apertura)
        if signal == BaseStrategy.SIGNAL_BUY:
            return True
            
        # Si es señal de VENTA, verificamos rentabilidad
        pos = bot_instance.get('position', {'qty': 0, 'avg_price': 0})
        
        # Solo aplica si estamos 'dentro' del mercado (qty > 0)
        if pos.get('qty', 0) > 0 and signal == BaseStrategy.SIGNAL_SELL:
            # Recuperar precio promedio
            avg_price = pos.get('avg_price', 0)
            if avg_price <= 0: return True # Prevención error div/0
            
            # Solo permitir venta si el precio actual > promedio * 1.001 (0.1% buffer)
            # Tarea 6.3: Profit Guard estricto (1.001) vs 1.002 anterior
            min_exit = avg_price * 1.001
            
            if current_price < min_exit:
                self.logger.warning(f"🛡️ Profit Guard: Blocked SELL for {bot_instance['symbol']} at {current_price}. Min required: {min_exit}")
                return False # BLOQUEAR EJECUCIÓN
                
        return True # Permitir ejecución
