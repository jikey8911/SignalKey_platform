import logging
import pandas as pd
import os
import joblib
import importlib
from datetime import datetime
from typing import List, Dict, Any
from api.src.domain.services.strategy_trainer import StrategyTrainer
from api.src.domain.services.exchange_port import ExchangePort
from api.src.domain.strategies.base import BaseStrategy

# === STABLE / BLOCKED ===
# Flow: TRAINING (global models) + PREDICT
# - training: train_all_strategies, _fetch_training_data
# - predict: predict
# Cambios aquí requieren: re-run training + smoke test predict
# ========================
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
        # Import ModelManager (Singleton)
        from api.src.infrastructure.ai.model_manager import ModelManager
        self.model_manager = ModelManager()

    async def _fetch_training_data(
        self,
        symbols: List[str],
        timeframe: str,
        user_id: str = "default_user",
        socket_callback = None,
        days: int = 90,
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

        # Approx candles per day by timeframe to keep consistent training horizon
        tf = (timeframe or "1h").lower().strip()
        tf_to_cpd = {
            "1m": 1440, "3m": 480, "5m": 288, "15m": 96, "30m": 48,
            "1h": 24, "2h": 12, "4h": 6, "6h": 4, "12h": 2, "1d": 1,
        }
        candles_per_day = tf_to_cpd.get(tf, 24)
        target_limit = int(max(300, min(5000, days * candles_per_day)))

        for symbol in symbols:
            try:
                # Entrenamiento robusto: ventana aleatoria dentro de la historia.
                df = await self.exchange.get_historical_data(
                    symbol,
                    timeframe,
                    limit=target_limit,
                    use_random_date=True,
                    user_id=user_id
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

    async def _run_strategy_backtest(self, strategy_name: str, data: Dict[str, pd.DataFrame], market_type: str = "spot") -> Dict[str, Any]:
        """
        Ejecuta un backtest simulado para una estrategia específica usando su .pkl si existe.
        Calcula PnL acumulado, tasa de acierto y número de operaciones.
        """
        try:
            # Load model and strategy from Memory
            model = self.model_manager.get_model(strategy_name, market_type)
            if not model:
                return None
            StrategyClass = self.trainer.load_strategy_class(strategy_name, market_type)
            if not StrategyClass: return None
            
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

    async def train_all_strategies(self, symbols: List[str], timeframe: str, days: int, market_type: str = "spot", user_id: str = "default_user") -> Dict[str, Any]:
        """
        Ciclo de entrenamiento masivo y agnóstico segmentado por mercado.
        Orquesta la obtención de datos + Entrenamiento de Modelos de Estategia.
        """
        self.logger.info(f"Iniciando orquestación de entrenamiento para {len(symbols)} activos (User: {user_id}).")

        # Callback para sockets
        async def socket_callback(msg: str, type: str = "info"):
            if user_id and user_id != "default_user":
                from api.src.adapters.driven.notifications.socket_service import socket_service
                await socket_service.emit_to_user(user_id, "training_log", {"message": msg, "type": type})

        # 1. Obtención de Datasets (con fechas aleatorias para robustez)
        # Usar el método centralizado para obtener datos
        data_collection = await self._fetch_training_data(symbols, timeframe, user_id, socket_callback, days=days)

        if not data_collection:
            await socket_callback("❌ Training failed: No data collected.", "error")
            return {"status": "error", "message": "Fallo en la recolección de datos de entrenamiento."}

        try:
            # 2. Entrenar Modelos de Estrategia Individuales
            trained_models = await self.trainer.train_all(data_collection, market_type=market_type, emit_callback=socket_callback)
            self.logger.info(f"Modelos de estrategia ({market_type}) entrenados: {len(trained_models)}")
            
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

    async def get_available_models(self, market_type: str = None) -> List[str]:
        """Consulta el inventario de cerebros .pkl disponibles en el sistema."""
        return self.trainer.discover_strategies(market_type)

    def predict(self, symbol: str, timeframe: str, candles: List[Dict], market_type: str = "spot", strategy_name: str = "auto", current_position: Dict = None) -> Dict[str, Any]:
        """
        Inferencia Real-Time.
        Si strategy_name es 'auto' o se omite, se evalúan todas y se devuelve la que decida el sistema.
        """
        if not candles:
            return {"strategy": "HOLD", "confidence": 0.0, "reason": "No data"}
            
        df = pd.DataFrame(candles)
        
        # Inferencia para estrategias específicas
        if strategy_name != "auto":
            target_strategies = [strategy_name]
        else:
            target_strategies = self.trainer.discover_strategies(market_type)
            
        final_results = {}
        
        for strat_name in target_strategies:
            try:
                # Optimized for Sprint 2: Load from Memory
                model = self.model_manager.get_model(strat_name, market_type)
                if not model:
                    continue
                
                StrategyClass = self.trainer.load_strategy_class(strat_name, market_type)
                if not StrategyClass: continue
                strategy = StrategyClass()
                
                # S9: Pasar current_position a la estrategia
                df_features = strategy.apply(df.copy(), current_position=current_position)
                
                # S9.3: Inyectar Contexto de Posición para el Modelo (Match Training)
                pos = current_position or {}
                in_pos = 1 if pos.get('qty', 0) > 0 else 0
                avg_price = pos.get('avg_price', 0)
                current_price = df.iloc[-1]['close']
                current_pnl = (current_price - avg_price) / avg_price if avg_price > 0 else 0.0
                
                df_features['in_position'] = in_pos
                df_features['current_pnl'] = current_pnl
                
                base_features = strategy.get_features() 
                features = base_features + ['in_position', 'current_pnl']
                
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
        strategy_used = strategy_name
        
        if strategy_name != "auto":
            decision = final_results.get(strategy_name, {}).get("action", "HOLD")
        else:
            # CORRECCIÓN: Usar target_strategies
            if target_strategies:
                # Por ahora tomamos la primera, pero aquí podrías filtrar por la que tenga mayor 'confidence'
                best_strat = target_strategies[0] 
                decision = final_results.get(best_strat, {}).get("action", "HOLD")
                strategy_used = best_strat
            else:
                decision = "HOLD"
            
        return {
            "symbol": symbol,
            "decision": decision,
            "analysis": final_results,
            "strategy_used": strategy_name
        }

    async def get_models_status(self, market_type: str = "spot") -> List[Dict[str, Any]]:
        """
        Obtiene el estado de todos los modelos entrenados disponibles para un mercado.
        """
        strategies = self.trainer.discover_strategies(market_type)
        models_status = []
        
        for strat in strategies:
            # Check specific then root
            model_path_specific = os.path.join(self.models_dir, market_type.lower(), f"{strat}.pkl").replace('\\', '/')
            model_path_root = os.path.join(self.models_dir, f"{strat}.pkl").replace('\\', '/')
            
            model_path = model_path_specific
            is_trained = os.path.exists(model_path)
            
            if not is_trained and os.path.exists(model_path_root):
                model_path = model_path_root
                is_trained = True
            
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
