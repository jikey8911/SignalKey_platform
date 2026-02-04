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
    market_type: str = "spot" # "spot" o "futures"
    mode: str = "simulated"   # "simulated" o "real"
    status: str = "paused"   # "active" o "paused" (Persistido en DB para resiliencia)
    config: Dict = field(default_factory=dict) # Parametros especificos de la estrategia
    position: Dict = field(default_factory=dict) # Estado de la posición actual
    last_execution: Optional[datetime] = None
    last_signal_at: Optional[datetime] = None
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    
    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "name": self.name,
            "symbol": self.symbol,
            "strategy_name": self.strategy_name,
            "timeframe": self.timeframe,
            "market_type": self.market_type,
            "mode": self.mode,
            "status": self.status,
            "config": self.config,
            "position": self.position,
            "last_execution": self.last_execution.isoformat() if self.last_execution else None,
            "last_signal_at": self.last_signal_at.isoformat() if self.last_signal_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }
