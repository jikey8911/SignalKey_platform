import sys
import os
import importlib

# Add project root to path
sys.path.append(os.getcwd())

from api.src.domain.services.strategy_trainer import StrategyTrainer

def check_strategies():
    print("🔍 Diagnosticando estrategias...")
    trainer = StrategyTrainer()
    
    # 1. Discover
    strategies = trainer.discover_strategies("spot")
    print(f"📋 Estrategias encontradas (spot): {strategies}")
    
    # 2. Try loading VWAP specifically
    if "vwap" in strategies:
        print("✅ VWAP encontrado en lista.")
        klass = trainer.load_strategy_class("vwap", "spot")
        if klass:
             print(f"✅ Clase cargada: {klass.__name__}")
        else:
             print("❌ Error cargando clase VWAP")
    else:
        print("❌ VWAP no encontrado por el trainer.")

    # 3. Validation of Directory
    strat_dir = os.path.join(os.getcwd(), "api/src/domain/strategies/spot")
    if os.path.exists(strat_dir):
        print(f"📂 Directorio existe: {strat_dir}")
        print(f"📂 Contenido: {os.listdir(strat_dir)}")
    else:
        print(f"❌ Directorio NO existe: {strat_dir}")

if __name__ == "__main__":
    check_strategies()
