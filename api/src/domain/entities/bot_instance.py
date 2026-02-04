from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict

@dataclass
class BotInstance:
    """
    Entidad de dominio sp2 que representa un bot activo o simulado.
    El estado 'status' permite que el sistema sepa si debe reanudar la operacion tras un reinicio.
    """
    id: Optional[str]
    user_id: str
    name: str
    symbol: str
    strategy_name: str
    timeframe: str
    mode: str = "simulated"  # "simulated" o "real"
    status: str = "paused"   # "active" o "paused" (Persistido en DB para resiliencia)
    config: Dict = field(default_factory=dict) # Parametros especificos de la estrategia
    created_at: datetime = field(default_factory=datetime.now)
    last_signal_at: Optional[datetime] = None
    last_execution: Optional[datetime] = None
    
    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "name": self.name,
            "symbol": self.symbol,
            "strategy_name": self.strategy_name,
            "timeframe": self.timeframe,
            "mode": self.mode,
            "status": self.status,
            "config": self.config,
            "created_at": self.created_at.isoformat(),
            "last_signal_at": self.last_signal_at.isoformat() if self.last_signal_at else None,
            "last_execution": self.last_execution.isoformat() if self.last_execution else None
        }
