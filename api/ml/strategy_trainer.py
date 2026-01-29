import os
import importlib
import pandas as pd
import joblib
import logging
from typing import Dict, List, Optional
from sklearn.ensemble import RandomForestClassifier

# Configure logger
logger = logging.getLogger("StrategyTrainer")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO)

class StrategyTrainer:
    """
    Motor de entrenamiento que carga estrategias dinámicamente y genera 
    modelos capaces de operar en cualquier símbolo (Agnósticos).
    """
    def __init__(self, strategies_dir: str = "api/strategies", models_dir: str = "api/data/models"):
        # Adjust paths to be relative to project root if needed
        # Assuming running from project root e:\antigravity\signaalKei_platform
        self.strategies_dir = strategies_dir
        self.models_dir = models_dir
        os.makedirs(self.models_dir, exist_ok=True)

    def discover_strategies(self) -> List[str]:
        """Busca archivos de estrategia válidos en el directorio."""
        if not os.path.exists(self.strategies_dir):
            logger.warning(f"Strategies directory {self.strategies_dir} does not exist.")
            return []
            
        return [file_name[:-3] for file_name in os.listdir(self.strategies_dir) 
                if file_name.endswith(".py") and file_name != "base.py" and not file_name.startswith("__")]

    def load_strategy_class(self, strategy_name: str):
        """Dynamic strategy class loading."""
        try:
            module_path = f"api.strategies.{strategy_name}"
            module = importlib.import_module(module_path)
            
            # Try snake_case to PascalCase conversion first
            class_name_pascal = "".join(w.title() for w in strategy_name.split("_"))
            
            if hasattr(module, class_name_pascal):
                return getattr(module, class_name_pascal)
            elif hasattr(module, strategy_name): # Fallback to filename as classname
                return getattr(module, strategy_name)
            else:
                logger.error(f"Class {class_name_pascal} or {strategy_name} not found in {module_path}")
                return None
        except Exception as e:
            logger.error(f"Error loading strategy {strategy_name}: {e}")
            return None

    def train_agnostic_model(self, strategy_name: str, symbols_data: Dict[str, pd.DataFrame]):
        """
        Entrena un modelo global para una estrategia usando datos de múltiples activos.
        """
        try:
            # Importación dinámica del módulo de estrategia
            StrategyClass = self.load_strategy_class(strategy_name)
            if not StrategyClass: return False
            
            strategy = StrategyClass()

            datasets = []
            for symbol, df in symbols_data.items():
                logger.info(f"Procesando patrones de {symbol} con {strategy_name}...")
                processed = strategy.apply(df.copy()).dropna()
                if not processed.empty:
                    # Rename 'signal' to 'label' if strategy outputs 'signal' 
                    # Use 'signal' as label 
                    datasets.append(processed)

            if not datasets: 
                logger.warning(f"No valid data found for {strategy_name}")
                return False

            # Combinación de datos de todos los símbolos (Entrenamiento Agnóstico)
            full_dataset = pd.concat(datasets)
            
            # Selección de características (Features) - Dynamic
            # Default features if strategy doesn't specify
            features = getattr(strategy, 'get_features', lambda: ['dev_pct', 'trend', 'hour', 'minute', 'day_week', 'relative_strength'])()
            
            # Verify features exist in dataset
            missing_cols = [c for c in features if c not in full_dataset.columns]
            if missing_cols:
                logger.error(f"Missing features in dataset for {strategy_name}: {missing_cols}")
                return False

            X = full_dataset[features]
            y = full_dataset['signal']

            # Entrenamiento del clasificador
            model = RandomForestClassifier(n_estimators=100, random_state=42)
            model.fit(X, y)

            # Persistencia: Un solo modelo por estrategia
            model_file = os.path.join(self.models_dir, f"{strategy_name}.pkl")
            joblib.dump(model, model_file)
            
            logger.info(f"Modelo {strategy_name}.pkl generado exitosamente.")
            return True
        except Exception as e:
            logger.error(f"Error en entrenamiento de {strategy_name}: {e}")
            return False

    def train_all(self, symbols_data: Dict[str, pd.DataFrame]):
        """Entrena todas las estrategias disponibles."""
        strategies = self.discover_strategies()
        results = {}
        for strat in strategies:
            success = self.train_agnostic_model(strat, symbols_data)
            results[strat] = "Success" if success else "Failed"
        return results
