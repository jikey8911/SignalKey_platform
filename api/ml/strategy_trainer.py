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

    async def train_agnostic_model(self, strategy_name: str, symbols_data: Dict[str, pd.DataFrame], emit_callback=None):
        """
        Entrena un modelo global para una estrategia usando datos de múltiples activos.
        """
        try:
            # Importación dinámica del módulo de estrategia
            StrategyClass = self.load_strategy_class(strategy_name)
            if not StrategyClass: return False
            
            strategy = StrategyClass()
            
            msg_start = f"💎 [StrategyTrainer] Using Virtual Balance Validation for {strategy_name} (No Exchange Ops)"
            print(msg_start)
            if emit_callback: await emit_callback(f"🚀 Starting training for {strategy_name}...", "info")

            datasets = []
            for symbol, df in symbols_data.items():
                logger.info(f"Procesando patrones de {symbol} con {strategy_name}...")
                processed = strategy.apply(df.copy()).dropna()
                if not processed.empty:
                    # Rename 'signal' to 'label' if strategy outputs 'signal' 
                    # Use 'signal' as label 
                    datasets.append(processed)

            if not datasets: 
                msg = f"⚠️ [StrategyTrainer] No valid data found for {strategy_name}"
                logger.warning(msg)
                print(msg)
                if emit_callback: await emit_callback(msg, "warning")
                return False

            # Combinación de datos de todos los símbolos (Entrenamiento Agnóstico)
            full_dataset = pd.concat(datasets)
            
            # --- TASK 5.1: Contexto de Posición ---
            # En lugar de usar los datos crudos, inyectamos el estado simulado
            full_dataset = self._apply_position_context(full_dataset)
            # -------------------------------------
            
            # Selección de características (Features) - Dynamic
            # Enforce strict contract: Strategy MUST implement get_features
            features = strategy.get_features()
            
            if not features:
                 msg = f"❌ [StrategyTrainer] Strategy {strategy_name} returned empty features list."
                 logger.error(msg)
                 if emit_callback: await emit_callback(msg, "error")
                 return False

            # Verify features exist in dataset
            missing_cols = [c for c in features if c not in full_dataset.columns]
            if missing_cols:
                msg = f"❌ [StrategyTrainer] Missing features for {strategy_name}: {missing_cols}"
                logger.error(msg)
                print(msg)
                if emit_callback: await emit_callback(msg, "error")
                return False

            X = full_dataset[features]
            y = full_dataset['signal']

            # Entrenamiento del clasificador
            msg_train = f"🧠 [StrategyTrainer] Training {strategy_name} on {len(X)} samples with features: {features}..."
            print(msg_train)
            if emit_callback: await emit_callback(msg_train, "info")
            
            model = RandomForestClassifier(n_estimators=100, random_state=42)
            model.fit(X, y)

            # Persistencia: Un solo modelo por estrategia
            model_file = os.path.join(self.models_dir, f"{strategy_name}.pkl")
            joblib.dump(model, model_file)
            
            logger.info(f"Modelo {strategy_name}.pkl generado exitosamente.")
            msg_success = f"✅ [StrategyTrainer] Saved model: {strategy_name}.pkl"
            print(msg_success)
            if emit_callback: await emit_callback(msg_success, "success")
            
            return True
        except Exception as e:
            logger.error(f"Error en entrenamiento de {strategy_name}: {e}")
            print(f"❌ [StrategyTrainer] Error training {strategy_name}: {e}")
            if emit_callback: await emit_callback(f"Error training {strategy_name}: {e}", "error")
            return False

    async def train_all(self, symbols_data: Dict[str, pd.DataFrame], emit_callback=None):
        """Entrena todas las estrategias disponibles."""
        strategies = self.discover_strategies()
        print(f"📋 [StrategyTrainer] Found {len(strategies)} strategies to train: {strategies}")
        if emit_callback: await emit_callback(f"📋 Found {len(strategies)} strategies", "info")
        
        results = {}
        for strat in strategies:
            success = await self.train_agnostic_model(strat, symbols_data, emit_callback)
            results[strat] = "Success" if success else "Failed"
        print(f"🏁 [StrategyTrainer] Training complete. Results: {results}")
        if emit_callback: await emit_callback("🏁 Training complete", "success")
        return results

    def _apply_position_context(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Tarea 5.1: Simula una trayectoria de posición para que la IA aprenda 
        que si el PnL es negativo, debe buscar un DCA o esperar.
        """
        # Evitar SettingWithCopyWarning
        df = df.copy().reset_index(drop=True)
        
        # Inicializar columnas de estado
        df['in_position'] = 0
        df['current_pnl'] = 0.0
        df['dca_count'] = 0
        
        pos_avg = 0.0
        is_open = False
        count = 0
        
        # Recorrido para etiquetado de contexto
        # Comenzamos desde el índice 1 para tener historial
        for i in range(1, len(df)):
            # Lógica simplificada: Si la estrategia base (o label previo) fue COMPRA (1)
            # Asumimos que la columna 'signal' ya viene pre-calculada por strategy.apply()
            # y contiene las señales ideales de la estrategia base.
            
            prev_signal = df.iloc[i-1]['signal']
            
            # Apertura / DCA
            if prev_signal == 1: 
                is_open = True
                count += 1
                # Promediar precio
                new_price = df.iloc[i]['close']
                pos_avg = ((pos_avg * (count-1)) + new_price) / count
                
            if is_open:
                df.at[i, 'in_position'] = 1
                df.at[i, 'dca_count'] = count
                if pos_avg > 0:
                    df.at[i, 'current_pnl'] = (df.iloc[i]['close'] - pos_avg) / pos_avg
                
                # Cierre (Venta simulada)
                if prev_signal == 2:
                    is_open = False
                    pos_avg = 0.0
                    count = 0
                    
        return df
