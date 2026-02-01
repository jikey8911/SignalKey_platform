import logging
from typing import List, Dict, Tuple

logger = logging.getLogger("RiskManager")

class RiskManager:
    """
    Tarea 7.1: Global Risk Manager (El "Kill Switch")
    Valida el Drawdown máximo y la exposición total antes de permitir que cualquier bot abra una nueva posición.
    """
    def __init__(self, global_config: dict = None):
        if global_config is None:
            global_config = {}
        
        # Default 10% Max Drawdown, $1000 Max Exposure
        self.max_drawdown = global_config.get('max_drawdown', 0.10) 
        self.max_exposure = global_config.get('max_exposure_usd', 1000.0)
        
        logger.info(f"🛡️ Risk Manager initialized. Max DD: {self.max_drawdown*100}%, Max Exposure: ${self.max_exposure}")

    async def can_open_position(self, current_balance: float, active_positions: List[Dict]) -> Tuple[bool, str]:
        """
        Verifica si el riesgo total permite una nueva operación.
        
        Args:
            current_balance: Balance total actual de la cuenta (Equity).
            active_positions: Lista de posiciones activas. Cada una debe tener 'pnl' y 'cost'.
            
        Returns:
            Tuple[bool, str]: (Allowed, Reason)
        """
        try:
            # Calcular PnL No Realizado Total
            total_unrealized_pnl = sum([p.get('pnl', 0.0) for p in active_positions])
            
            # Calcular Drawdown Actual (% de pérdida florante sobre el balance)
            # Evitar división por cero
            if current_balance <= 0:
                logger.warning("RiskManager: Current balance is 0 or negative.")
                return False, "Balance insuficiente"

            current_drawdown = 0.0
            if total_unrealized_pnl < 0:
               current_drawdown = abs(total_unrealized_pnl) / current_balance
            
            if current_drawdown > self.max_drawdown:
                logger.warning(f"⛔ risk_manager: Max Drawdown reached ({current_drawdown*100:.2f}% > {self.max_drawdown*100:.2f}%)")
                return False, f"Drawdown máximo alcanzado ({current_drawdown*100:.2f}%)"
                
            # Calcular Exposición Total (Dinero invertido)
            total_invested = sum([p.get('cost', 0.0) for p in active_positions])
            
            if total_invested >= self.max_exposure:
                logger.warning(f"⛔ risk_manager: Max Exposure reached (${total_invested} >= ${self.max_exposure})")
                return False, f"Exposición máxima alcanzada (${total_invested})"
                
            return True, "OK"
            
        except Exception as e:
            logger.error(f"Error in RiskManager: {e}")
            # En caso de error, por seguridad bloqueamos
            return False, f"Error de verificación de riesgo: {str(e)}"
