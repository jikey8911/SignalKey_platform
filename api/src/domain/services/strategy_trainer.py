import os
import importlib
import pandas as pd
import numpy as np
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
    def __init__(self, strategies_dir: str = "api/src/domain/strategies", models_dir: str = "api/data/models"):
        # Adjust paths to be relative to project root if needed
        # Assuming running from project root e:\antigravity\signaalKei_platform
        self.strategies_dir = strategies_dir
        self.models_dir = models_dir
        os.makedirs(self.models_dir, exist_ok=True)

    def discover_strategies(self, market_type: str = None) -> List[str]:
        """Busca archivos de estrategia válidos en el directorio raíz y subdirectorios de mercado."""
        strategies = set()
        
        # 1. Search in market specific subdirectory if provided (Priority)
        if market_type:
            market_dir = os.path.join(self.strategies_dir, market_type.lower())
            if os.path.exists(market_dir):
                market_files = [f[:-3] for f in os.listdir(market_dir) 
                                if f.endswith(".py") and f != "base.py" and not f.startswith("__")]
                strategies.update(market_files)

        # 2. Search in root strategies directory
        if os.path.exists(self.strategies_dir):
            root_files = [f[:-3] for f in os.listdir(self.strategies_dir)
                          if f.endswith(".py") and f != "base.py" and not f.startswith("__")
                          and not os.path.isdir(os.path.join(self.strategies_dir, f))]
            strategies.update(root_files)

        if not strategies:
             logger.warning(f"No strategies found in {self.strategies_dir} (market: {market_type})")
             return []
             
        return sorted(list(strategies))

    def load_strategy_class(self, strategy_name: str, market_type: str = None):
        """Dynamic strategy class loading by scanning for BaseStrategy subclasses."""
        from api.src.domain.strategies.base import BaseStrategy
        import inspect

        try:
            if market_type:
                module_path = f"api.src.domain.strategies.{market_type.lower()}.{strategy_name}"
            else:
                module_path = f"api.src.domain.strategies.{strategy_name}"

            try:
                module = importlib.import_module(module_path)
            except ImportError:
                # Fallback to root strategies if market-specific not found
                if market_type:
                    module_path = f"api.src.domain.strategies.{strategy_name}"
                    module = importlib.import_module(module_path)
                else:
                    raise
            
            # Scan for any class that inherits from BaseStrategy
            for name, obj in inspect.getmembers(module):
                if inspect.isclass(obj) and issubclass(obj, BaseStrategy) and obj is not BaseStrategy:
                    return obj
            
            # If no class found via scan, try the legacy naming convention as fallback
            class_name_pascal = "".join(w.title() for w in strategy_name.split("_"))
            if hasattr(module, class_name_pascal):
                return getattr(module, class_name_pascal)
            elif hasattr(module, strategy_name):
                return getattr(module, strategy_name)

            logger.error(f"No BaseStrategy subclass found in {module_path}")
            return None

        except Exception as e:
            logger.error(f"Error loading strategy {strategy_name}: {e}")
            return None

    async def train_agnostic_model(self, strategy_name: str, symbols_data: Dict[str, pd.DataFrame], market_type: str = "spot", emit_callback=None):
        """
        Entrena un modelo global para una estrategia usando datos de múltiples activos.
        Segmentado por market_type.
        """
        try:
            # Importación dinámica del módulo de estrategia
            StrategyClass = self.load_strategy_class(strategy_name, market_type)
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
            full_dataset = self._inject_position_context(full_dataset)
            # -------------------------------------
            
            # Selección de características (Features) - Dynamic
            # Enforce strict contract: Strategy MUST implement get_features
            # --- AGREGAR CONTEXTO A LAS FEATURES ---
            # Las estrategias ahora aprenden de los indicadores + el estado de la posición
            base_features = strategy.get_features()
            ml_features = base_features + ['in_position', 'current_pnl']
            
            if not ml_features:
                 msg = f"❌ [StrategyTrainer] Strategy {strategy_name} returned empty features list."
                 logger.error(msg)
                 if emit_callback: await emit_callback(msg, "error")
                 return False

            # Verify features exist in dataset
            missing_cols = [c for c in ml_features if c not in full_dataset.columns]
            if missing_cols:
                msg = f"❌ [StrategyTrainer] Missing features for {strategy_name}: {missing_cols}"
                logger.error(msg)
                print(msg)
                if emit_callback: await emit_callback(msg, "error")
                return False

            # Clean dataset from Infs/NaNs before training
            full_dataset[ml_features] = full_dataset[ml_features].replace([np.inf, -np.inf], np.nan)
            full_dataset = full_dataset.dropna(subset=ml_features + ['signal'])

            if full_dataset.empty:
                msg = f"❌ [StrategyTrainer] Dataset became empty after dropping NaNs/Infs for {strategy_name}."
                logger.error(msg)
                if emit_callback: await emit_callback(msg, "error")
                return False

            X = full_dataset[ml_features]
            y = full_dataset['signal']

            # Entrenamiento del clasificador con mayor profundidad para captar las reglas de PnL
            msg_train = f"🧠 [StrategyTrainer] Training {strategy_name} on {len(X)} samples with features: {ml_features}..."
            print(msg_train)
            if emit_callback: await emit_callback(msg_train, "info")
            
            model = RandomForestClassifier(n_estimators=150, max_depth=10, random_state=42)
            model.fit(X, y)

            # Persistencia segmentada por mercado
            market_dir = os.path.join(self.models_dir, market_type.lower()).replace('\\', '/')
            os.makedirs(market_dir, exist_ok=True)

            model_file = os.path.join(market_dir, f"{strategy_name}.pkl").replace('\\', '/')
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

    async def train_all(self, symbols_data: Dict[str, pd.DataFrame], market_type: str = "spot", emit_callback=None):
        """Entrena todas las estrategias disponibles."""
        strategies = self.discover_strategies(market_type)
        print(f"📋 [StrategyTrainer] Found {len(strategies)} strategies to train for {market_type}: {strategies}")
        if emit_callback: await emit_callback(f"📋 Found {len(strategies)} strategies for {market_type}", "info")
        
        results = {}
        for strat in strategies:
            success = await self.train_agnostic_model(strat, symbols_data, market_type, emit_callback)
            results[strat] = "Success" if success else "Failed"
        print(f"🏁 [StrategyTrainer] Training complete. Results: {results}")
        if emit_callback: await emit_callback("🏁 Training complete", "success")
        return results

    def _inject_position_context(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Inyección de Contexto (Long/Short flipping).
        Enseña a la IA que si hay pérdida, no debe flippear (Profit Guard), debe esperar o promediar.
        """
        df = df.copy()
        df['in_position'] = 0
        df['current_pnl'] = 0.0
        
        avg_price = 0.0
        in_pos = False
        current_side = None
        
        for i in range(1, len(df)):
            current_close = df.iloc[i]['close']
            # Obtener la señal original de la estrategia técnica
            original_signal = df.iloc[i]['signal']
            
            if in_pos:
                df.at[df.index[i], 'in_position'] = 1
                
                # Calcular PnL según dirección
                if current_side == "BUY":
                    pnl = (current_close - avg_price) / avg_price
                else:
                    pnl = (avg_price - current_close) / avg_price
                    
                df.at[df.index[i], 'current_pnl'] = pnl

                # PROFIT GUARD TRAINING:
                # Si la señal es contraria pero el PnL es negativo, enseñamos a ESPERAR (0)
                is_reversal = (current_side == "BUY" and original_signal == 2) or \
                              (current_side == "SELL" and original_signal == 1)

                if is_reversal and pnl < -0.005: # -0.5% margen
                    df.at[df.index[i], 'signal'] = 0 # WAIT

                # Actualizar estado si hubo flip exitoso (o entrada inicial)
                if original_signal == 1:
                    current_side = "BUY"
                    avg_price = current_close
                elif original_signal == 2:
                    current_side = "SELL"
                    avg_price = current_close
            else:
                if original_signal == 1:
                    in_pos = True
                    current_side = "BUY"
                    avg_price = current_close
                elif original_signal == 2:
                    in_pos = True
                    current_side = "SELL"
                    avg_price = current_close
                    
        return df
