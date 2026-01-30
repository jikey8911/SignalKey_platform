import logging
import pandas as pd
import os
import joblib
import importlib
from datetime import datetime
from typing import List, Dict, Any
from api.ml.strategy_trainer import StrategyTrainer
from api.src.domain.services.exchange_port import ExchangePort
from api.strategies.base import BaseStrategy

class MLService:
    """
    Orquestador de Machine Learning de la Capa de Aplicación (sp4).
    
    Esta versión resuelve la incompatibilidad técnica eliminando cualquier referencia 
    a modelos específicos (como el antiguo LSTM) o columnas fijas (RSI, ADX). 
    Ahora actúa como un puente limpio que recolecta datos y delega la 'inteligencia' 
    al StrategyTrainer y las estrategias dinámicas.
    """
    def __init__(self, exchange_adapter: ExchangePort, trainer: StrategyTrainer = None):
        self.exchange = exchange_adapter
        self.trainer = trainer or StrategyTrainer()
        self.logger = logging.getLogger("MLService")
        self.models_dir = "api/data/models"

    async def _fetch_training_data(
        self, 
        symbols: List[str], 
        timeframe: str, 
        user_id: str = "default_user",
        socket_callback = None
    ) -> Dict[str, pd.DataFrame]:
        """
        Método centralizado para obtener datos históricos de entrenamiento.
        Usa API pública con fechas aleatorias para robustez.
        
        Args:
            symbols: Lista de símbolos a obtener
            timeframe: Timeframe de las velas (e.g., '1h', '4h')
            user_id: ID del usuario para logs
            socket_callback: Callback opcional para emitir logs via socket
            
        Returns:
            Dict con {symbol: DataFrame} de datos históricos
        """
        data_collection = {}
        
        for symbol in symbols:
            try:
                # Usamos random_date=True para el entrenamiento y API pública
                df = await self.exchange.get_public_historical_data(
                    symbol, 
                    timeframe, 
                    limit=2000, 
                    use_random_date=True, 
                    exchange_id="binance"
                )
                
                if not df.empty:
                    data_collection[symbol] = df
                    self.logger.info(f"Dataset de entrenamiento listo para {symbol}: {len(df)} velas.")
                    if socket_callback:
                        await socket_callback(f"📉 Loaded {len(df)} candles for {symbol}", "info")
            except Exception as e:
                self.logger.error(f"No se pudo obtener datos para {symbol}: {e}")
                if socket_callback:
                    await socket_callback(f"⚠️ Failed to load data for {symbol}: {e}", "warning")
        
        return data_collection

    async def _run_strategy_backtest(self, strategy_name: str, data: Dict[str, pd.DataFrame]) -> Dict[str, Any]:
        """
        Ejecuta un backtest simulado para una estrategia específica usando su .pkl si existe.
        Calcula PnL acumulado, tasa de acierto y número de operaciones.
        """
        model_path = os.path.join(self.models_dir, f"{strategy_name}.pkl")
        if not os.path.exists(model_path):
            return None
            
        try:
            # Load model and strategy
            model = joblib.load(model_path)
            StrategyClass = self.trainer.load_strategy_class(strategy_name)
            if not StrategyClass: return None
            
            strategy = StrategyClass()
            strategy = StrategyClass()
            features = strategy.get_features()
            
            total_pnl = 0.0
            trades_count = 0
            winning_trades = 0
            
            for symbol, df in data.items():
                processed = strategy.apply(df.copy())
                
                # Check for required features
                missing = [c for c in features if c not in processed.columns]
                if missing: 
                    self.logger.warning(f"Strategy {strategy_name} missing features for {symbol}: {missing}")
                    continue
                
                # Use only rows where features are not NaN
                X = processed[features].dropna()
                if X.empty: continue
                
                # Predict signals: 1 (Buy), -1 (Sell), 0 (Wait)
                predictions = model.predict(X)
                
                # Calculate returns (using next candle close for profit calculation)
                # profit = signal_t * ((close_{t+1} / close_t) - 1)
                df_aligned = processed.loc[X.index]
                returns = df_aligned['close'].pct_change().shift(-1).fillna(0)
                
                strat_returns = predictions * returns
                
                total_pnl += strat_returns.sum()
                trades_count += (predictions != 0).sum()
                winning_trades += (strat_returns > 0).sum()

            if trades_count == 0: return None

            return {
                "name": strategy_name,
                "pnl": round(total_pnl * 100, 2), # Percentage
                "trades": int(trades_count),
                "win_rate": round((winning_trades / trades_count * 100), 2)
            }
        except Exception as e:
            self.logger.error(f"Error backtesting {strategy_name}: {e}")
            return None

    async def train_all_strategies(self, symbols: List[str], timeframe: str, days: int, user_id: str = "default_user") -> Dict[str, Any]:
        """
        Ciclo de entrenamiento masivo y agnóstico.
        Orquesta la obtención de datos + Entrenamiento de Modelos de Estategia + Entrenamiento del Selector.
        """
        self.logger.info(f"Iniciando orquestación de entrenamiento para {len(symbols)} activos (User: {user_id}).")

        # Callback para sockets
        async def socket_callback(msg: str, type: str = "info"):
            if user_id and user_id != "default_user":
                from api.src.adapters.driven.notifications.socket_service import socket_service
                await socket_service.emit_to_user(user_id, "training_log", {"message": msg, "type": type})

        # 1. Obtención de Datasets (con fechas aleatorias para robustez)
        # Usar el método centralizado para obtener datos
        data_collection = await self._fetch_training_data(symbols, timeframe, user_id, socket_callback)

        if not data_collection:
            await socket_callback("❌ Training failed: No data collected.", "error")
            return {"status": "error", "message": "Fallo en la recolección de datos de entrenamiento."}

        try:
            # 2. Entrenar Modelos de Estrategia Individuales
            trained_models = await self.trainer.train_all(data_collection, emit_callback=socket_callback)
            self.logger.info(f"Modelos de estrategia entrenados: {len(trained_models)}")
            
            # 3. Entrenar Meta-Modelo (Selector) - YA NO ES AUTOMÁTICO
            # Se ha desacoplado a petición del usuario para ser un paso manual.
            
            return {
                "status": "success",
                "trained_count": len(trained_models),
                "models_generated": trained_models,
                "symbols_used": list(data_collection.keys())
            }
        except Exception as e:
            self.logger.error(f"Fallo crítico en el proceso de entrenamiento: {e}")
            await socket_callback(f"❌ Critical Error: {e}", "error")
            return {"status": "error", "message": f"Error en motor ML: {str(e)}"}

    async def get_available_models(self) -> List[str]:
        """Consulta el inventario de cerebros .pkl disponibles en el sistema."""
        return self.trainer.discover_strategies()

    def predict(self, symbol: str, timeframe: str, candles: List[Dict], strategy_name: str = "auto") -> Dict[str, Any]:
        """
        Inferencia Real-Time.
        Si strategy_name es 'auto' o se omite, se evalúan todas y se devuelve la que decida el sistema.
        """
        if not candles:
            return {"strategy": "HOLD", "confidence": 0.0, "reason": "No data"}
            
        df = pd.DataFrame(candles)
        
        # Inferencia para estrategias específicas
        strategies = self.trainer.discover_strategies()
        if strategy_name != "auto" and strategy_name in strategies:
            target_strategies = [strategy_name]
        else:
            target_strategies = strategies
            
        final_results = {}
        
        for strat_name in target_strategies:
            try:
                model_path = os.path.join(self.models_dir, f"{strat_name}.pkl")
                if not os.path.exists(model_path): continue
                model = joblib.load(model_path)
                
                module = importlib.import_module(f"api.strategies.{strat_name}")
                class_name = "".join(w.title() for w in strat_name.split("_"))
                StrategyClass = getattr(module, class_name)
                strategy = StrategyClass()
                
                df_features = strategy.apply(df.copy())
                features = strategy.get_features() 
                
                if df_features.empty or not all(c in df_features.columns for c in features): continue
                
                last_row = df_features.iloc[[-1]][features]
                pred = model.predict(last_row)[0]
                
                action = "HOLD"
                if pred == BaseStrategy.SIGNAL_BUY: action = "BUY"
                elif pred == BaseStrategy.SIGNAL_SELL: action = "SELL"
                
                final_results[strat_name] = {"action": action}
                
            except: continue
            
        # Determinar decisión final
        decision = "HOLD"
        if strategy_name != "auto":
            decision = final_results.get(strategy_name, {}).get("action", "HOLD")
        else:
            decision = final_results.get(strategies[0], {}).get("action", "HOLD") if strategies else "HOLD"
            
        return {
            "symbol": symbol,
            "decision": decision,
            "analysis": final_results,
            "strategy_used": strategy_name
        }

    async def get_models_status(self) -> List[Dict[str, Any]]:
        """
        Obtiene el estado de todos los modelos entrenados disponibles.
        """
        strategies = self.trainer.discover_strategies()
        models_status = []
        
        for strat in strategies:
            model_path = os.path.join(self.models_dir, f"{strat}.pkl")
            is_trained = os.path.exists(model_path)
            
            last_trained = None
            if is_trained:
                mtime = os.path.getmtime(model_path)
                last_trained = datetime.fromtimestamp(mtime).isoformat()
            
            models_status.append({
                "id": strat,
                "name": strat.replace("_", " ").title(),
                "is_trained": is_trained,
                "last_trained": last_trained,
                "accuracy": 0.0, # Placeholder until we have metabolic metrics
                "strategy": strat
            })
            
        return models_status
