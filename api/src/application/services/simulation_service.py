import logging
from datetime import datetime
from bson import ObjectId
from api.src.domain.strategies.base import BaseStrategy

class SimulationService:
    """
    Servicio sp3 que gestiona el trading virtual.
    Calcula balances ficticios, aplica comisiones (fees) y registra PnL.
    """
    def __init__(self, db_adapter):
        self.db = db_adapter
        self.fee_rate = 0.001  # 0.1% de comisión simulada

    async def execute_trade(self, bot_instance, signal, price, amount):
        """
        Ejecuta operación virtual y persiste el log necesario para el Dashboard de PnL.
        """
        bot_id = bot_instance['id']
        side = "buy" if signal == BaseStrategy.SIGNAL_BUY else "sell"
        fee = amount * self.fee_rate
        
        # Log del trade optimizado para graficación posterior (Tarea 4.3/4.4)
        trade_log = {
            "bot_id": bot_id,
            "symbol": bot_instance['symbol'],
            "side": side,
            "price": price,
            "amount": amount,
            "fee": fee,
            "timestamp": datetime.now(),
            "mode": "simulated"
        }

        # 1. Guardar log en colección para reconstrucción de gráficos
        await self.db.db["simulation_trades"].insert_one(trade_log)

        # 2. Actualización de posición (DCA)
        current_pos = bot_instance.get('position', {'qty': 0, 'avg_price': 0})
        
        if side == "buy":
            new_qty = current_pos['qty'] + (amount / price)
            total_val = (current_pos['avg_price'] * current_pos['qty']) + (price * (amount / price))
            # Fix potential division by zero or simplify DCA math
            # Amount/Price = added qty.
            # Total Cost = Old Avg * Old Qty + New Spend (Amount)
            total_cost = (current_pos['avg_price'] * current_pos['qty']) + amount
            new_avg = total_cost / new_qty if new_qty > 0 else 0
            updated_pos = {'qty': new_qty, 'avg_price': new_avg}
        else:
            # Cierre de posición simplificado
            updated_pos = {'qty': 0, 'avg_price': 0}

        # 3. Sincronizar estado en MongoDB (Sprint 2)
        await self.db.db["bot_instances"].update_one(
            {"_id": ObjectId(bot_id)},
            {"$set": {"position": updated_pos, "last_execution": trade_log}}
        )

        return trade_log
