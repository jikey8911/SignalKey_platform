import logging
from typing import List, Dict, Tuple

class RiskManager:
    """
    PUERTO DE DOMINIO - Lógica de Riesgo (Tarea 7.1).
    Valida si una nueva operación es permitida basándose en el estado global.
    """
    def __init__(self, config: Dict = None):
        if config is None:
            config = {}
        # Configuración de límites (pueden venir de app_configs en MongoDB)
        self.max_drawdown = config.get('max_drawdown', 0.15) # 15% máximo
        self.max_exposure_usd = config.get('max_exposure_usd', 2000.0)
        self.max_bots_active = config.get('max_bots_active', 5)
        self.logger = logging.getLogger("RiskManager")
        self.logger.info(f"🛡️ Risk Manager domain service initialized. Max DD: {self.max_drawdown*100}%, Max Exposure: ${self.max_exposure_usd}")

    def validate_execution(self, 
                           current_balance: float, 
                           active_positions: List[Dict], 
                           new_order_amount: float) -> Tuple[bool, str]:
        """
        Determina si es seguro ejecutar una nueva orden.
        
        Args:
            current_balance: Balance disponible + valor de posiciones (Equity).
            active_positions: Lista de posiciones activas.
            new_order_amount: Monto en USD de la nueva orden invertida.
        
        Returns:
            Tuple[bool, str]: (Allowed, Reason)
        """
        try:
            # 1. Validar exposición total
            # Sumamos el costo de posiciones activas
            total_cost = sum([p.get('cost', 0.0) for p in active_positions])
            
            if (total_cost + new_order_amount) > self.max_exposure_usd:
                self.logger.warning(f"⛔ risk_manager: Max USD Exposure Exceeded (${total_cost + new_order_amount} > ${self.max_exposure_usd})")
                return False, "Exposición máxima excedida (Límite USD)"

            # 2. Validar Drawdown actual (PnL No Realizado)
            # Calculamos PnL flotante sumado
            total_unrealized_pnl = sum([p.get('unrealized_pnl', 0.0) for p in active_positions])
            
            # Drawdown = abs(perida) / balance
            current_dd = abs(total_unrealized_pnl) / current_balance if current_balance > 0 else 0
            
            # Solo bloqueamos si tenemos pérdidas y superan el umbral
            if total_unrealized_pnl < 0 and current_dd > self.max_drawdown:
                self.logger.warning(f"⛔ risk_manager: Max Drawdown Exceeded ({current_dd:.2%} > {self.max_drawdown:.2%})")
                return False, f"Drawdown crítico alcanzado: {current_dd:.2%}"

            # 3. Validar cantidad de bots operando (si cada bot tiene 1 posición max)
            # Esto asume que active_positions mapea 1:1 a bots, o es una lista de todas las posiciones.
            # Según snippet usuario: 'len(active_positions) >= self.max_bots_active'
            if len(active_positions) >= self.max_bots_active:
                self.logger.warning(f"⛔ risk_manager: Max Active Bots Limit ({len(active_positions)} >= {self.max_bots_active})")
                return False, "Máximo de hilos operativos alcanzado"

            return True, "Validación de riesgo exitosa"
            
        except Exception as e:
            self.logger.error(f"Error in validate_execution: {e}")
            # Fail-safe: Block on error
            return False, f"Error interno de riesgo: {str(e)}"
