import os
import joblib
import pandas as pd
import logging
import importlib
from typing import Dict, Any, List
from api.ml.strategy_trainer import StrategyTrainer
from api.ml.strategy_trainer import StrategyTrainer
from api.src.domain.services.exchange_port import IExchangePort

class BacktestService:
    """
    Servicio de Backtest de la Capa de Aplicación (sp4).
    
    Se ha eliminado toda lógica de columnas hardcoded ('por si acaso').
    Ahora confía al 100% en el contrato dinámico (get_features) de cada 
    estrategia para preparar los datos de entrada del modelo .pkl.
    """
    def __init__(self, exchange_adapter: IExchangePort, trainer: StrategyTrainer = None, models_dir: str = "api/data/models"):
        self.exchange = exchange_adapter
        self.trainer = trainer or StrategyTrainer()
        self.models_dir = models_dir
        self.logger = logging.getLogger("BacktestService")

    async def select_best_model(self, symbol: str, timeframe: str) -> Dict[str, Any]:
        """
        Evalúa todos los modelos agnósticos y recomienda el mejor para un activo,
        utilizando exclusivamente el contrato de features de la estrategia.
        """
        self.logger.info(f"Iniciando validación técnica para {symbol}...")
        
        # 1. Obtener datos históricos del exchange
        df = await self.exchange.get_historical_data(symbol, timeframe, limit=1000)
        if df.empty:
            return {"error": "Fallo al obtener datos históricos para validación."}

        strategies = self.trainer.discover_strategies()
        best_score = -1
        best_strat = None

        results = []
        for strat_name in strategies:
            try:
                model_path = os.path.join(self.models_dir, f"{strat_name}.pkl")
                if not os.path.exists(model_path):
                    continue
                
                # Cargar el modelo IA y la clase de estrategia correspondiente
                model = joblib.load(model_path)
                
                # Importación dinámica del contrato de la estrategia
                module = importlib.import_module(f"api.strategies.{strat_name}")
                class_name = "".join(w.title() for w in strat_name.split("_"))
                StrategyClass = getattr(module, class_name)
                strategy = StrategyClass()
                
                # 2. Aplicar procesamiento (Cálculo de indicadores)
                df_test = strategy.apply(df.copy()).dropna()
                if df_test.empty:
                    continue

                # 3. SINCRONIZACIÓN TOTAL
                features = strategy.get_features()
                missing = [c for c in features if c not in df_test.columns]
                if missing:
                    self.logger.error(f"Contrato roto en {strat_name}: Faltan columnas {missing}")
                    continue

                X = df_test[features]
                
                # 4. Predicción y Cálculo de Precisión
                predictions = model.predict(X)
                score = self._calculate_accuracy(df_test['signal'].values, predictions)
                
                # Calcular métricas básicas
                trades_count = (predictions != 0).sum()
                
                results.append({
                    "strategy": strat_name,
                    "accuracy": score,
                    "trades": int(trades_count),
                    "status": "active"
                })
                
                if score > best_score:
                    best_score = score
                    best_strat = strat_name

            except Exception as e:
                self.logger.error(f"Error analizando modelo {strat_name}: {e}")
                results.append({"strategy": strat_name, "error": str(e), "status": "failed"})

        return {
            "symbol": symbol,
            "recommended_strategy": best_strat,
            "accuracy_score": round(best_score, 4) if best_strat else 0,
            "tournament_results": results,
            "contract_status": "synced"
        }

    def _calculate_accuracy(self, y_true: Any, y_pred: Any) -> float:
        """Compara la señal ideal de la estrategia con la predicción de la IA."""
        if len(y_true) == 0: return 0.0
        matches = (y_true == y_pred).sum()
        return float(matches / len(y_true))