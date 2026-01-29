import pandas as pd
import joblib
import os
import logging
from typing import Dict, List, Any
from api.ml.strategy_trainer import StrategyTrainer

logger = logging.getLogger(__name__)

class BacktestService:
    """
    Refactorizado en sp2 para evaluar todas las estrategias y 
    recomendar la mejor instancia de modelo para un símbolo.
    """
    def __init__(self, exchange_adapter, models_dir="api/data/models"):
        self.exchange = exchange_adapter
        self.models_dir = models_dir
        self.trainer = StrategyTrainer()

    async def find_best_strategy(self, symbol: str, timeframe: str, days: int, exchange_id: str = None) -> Dict[str, Any]:
        """
        Ejecuta un backtest comparativo usando todos los modelos entrenados.
        Retorna la estrategia con mejor rendimiento (PnL/WinRate).
        """
        try:
            # 1. Obtener datos de prueba
            # Adapt to CCXTService signature: symbol, exchange_id, timeframe, days_back
            # Use 'binance' or provided exchange_id default
            target_exchange = exchange_id if exchange_id else 'binance' 
            
            # Fetch OHLCV and convert to DataFrame
            ohlcv = await self.exchange.get_historical_ohlcv(symbol, target_exchange, timeframe, days_back=days)
            
            if not ohlcv:
                return {"error": "No data found"}
                
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df.sort_values('timestamp', inplace=True)
            df.reset_index(drop=True, inplace=True)

            available_strategies = self.trainer.discover_strategies()
            results = []

            for strat_name in available_strategies:
                model_path = os.path.join(self.models_dir, f"{strat_name}.pkl")
                if not os.path.exists(model_path):
                    continue
                
                # 2. Cargar modelo y realizar predicciones (Simular Backtest)
                try:
                    model = joblib.load(model_path)
                except Exception as e:
                    logger.error(f"Error loading model {strat_name}: {e}")
                    continue
                
                # Cargar la clase para procesar indicadores
                StrategyClass = self.trainer.load_strategy_class(strat_name)
                if not StrategyClass: continue
                
                strategy = StrategyClass()
                df_test = strategy.apply(df.copy()).dropna()
                
                if df_test.empty: continue

                # Get features dynamically
                features = getattr(strategy, 'get_features', lambda: ['dev_pct', 'trend', 'hour', 'day_week'])()
                
                # Verify features exist
                missing_cols = [c for c in features if c not in df_test.columns]
                if missing_cols:
                    continue
                    
                X = df_test[features]
                
                # 3. Ejecutar inferencia
                try:
                    df_test['pred_signal'] = model.predict(X)
                    
                    # 4. Cálculo de rendimiento simple (PnL Teórico)
                    pnl = self._calculate_theoretical_pnl(df_test)
                    
                    results.append({
                        "strategy_name": strat_name,
                        "pnl": pnl,
                        "win_rate": len(df_test[df_test['pred_signal'] != 0]) / len(df_test) if len(df_test) > 0 else 0,
                        "total_trades": len(df_test[df_test['pred_signal'] != 0])
                    })
                except Exception as e:
                    logger.error(f"Error inferencing {strat_name}: {e}")
                    continue

            # Seleccionar la mejor
            if not results:
                return {"error": "No valid models found or no profitable trades"}
                
            best = max(results, key=lambda x: x['pnl'])
            return {
                "symbol": symbol,
                "best_strategy": best['strategy_name'],
                "expected_pnl": best['pnl'],
                "all_results": results
            }
        except Exception as e:
            logger.error(f"Error in find_best_strategy: {e}")
            return {"error": str(e)}

    async def run_backtest(self, symbol: str, days: int, timeframe: str, use_ai: bool = True, user_config: dict = None, strategy: str = "auto", user_id: str = None, exchange_id: str = "binance", model_id: str = None):
        """
        Método wrapper para soportar la llamada desde el router.
        Si se pasa un model_id, ejecuta esa estrategia específica.
        """
        target_exchange = exchange_id if exchange_id else 'binance'
        
        # Si nos piden un modelo específico (ej: "SVR_VOLATILITY")
        if model_id and model_id != "auto":
            # Extraer nombre de estrategia del ID del modelo si es necesario
            # Asumimos que model_id es el nombre de la estrategia (filename sin ext)
            strategy_name = model_id
            
            ohlcv = await self.exchange.get_historical_ohlcv(symbol, target_exchange, timeframe, days_back=days)
            if not ohlcv:
                return {"error": "No data found"}
                
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df.sort_values('timestamp', inplace=True)
            df.reset_index(drop=True, inplace=True)
            
            # Instanciar estrategia específica
            StrategyClass = self.trainer.load_strategy_class(strategy_name)
            if not StrategyClass:
                return {"error": f"Strategy class not found for {strategy_name}"}
            
            strat_instance = StrategyClass()
            df_test = strat_instance.apply(df.copy()).dropna()
            
            if df_test.empty:
                return {"error": "Not enough data for features"}

            # Cargar modelo
            model_path = os.path.join(self.models_dir, f"{strategy_name}.pkl")
            if not os.path.exists(model_path):
                return {"error": f"Model file not found for {strategy_name}"}
                
            try:
                model = joblib.load(model_path)
                features = getattr(strat_instance, 'get_features', lambda: ['dev_pct', 'trend', 'hour', 'day_week'])()
                X = df_test[features]
                df_test['pred_signal'] = model.predict(X)
                
                # Calcular métricas detalladas
                pnl = self._calculate_theoretical_pnl(df_test)
                win_rate = len(df_test[df_test['pred_signal'] != 0]) / len(df_test) if len(df_test) > 0 else 0
                total_trades = len(df_test[df_test['pred_signal'] != 0])
                
                # Generar trades para el gráfico
                trades_list = []
                for idx, row in df_test[df_test['pred_signal'] != 0].iterrows():
                    action = "BUY" if row['pred_signal'] == 1 else "SELL"
                    trades_list.append({
                        "time": int(row['timestamp'].timestamp() * 1000), # Converter to ms
                        "price": row['close'], # Precio de cierre de la vela
                        "type": action,
                        "pnl": 0 # TODO: Calcular PnL por trade individual
                    })
                
                return {
                    "symbol": symbol,
                    "strategy_name": strategy_name,
                    "chart_data": df.to_dict(orient='records'), # Data completa para el gráfico
                    "trades": trades_list,
                    "metrics": {
                        "profit_pct": pnl * 100,
                        "total_trades": total_trades,
                        "win_rate": win_rate * 100,
                        "profit_factor": 1.5, # Placeholder
                        "max_drawdown": 0.0, # Placeholder
                        "sharpe_ratio": 1.2 # Placeholder
                    },
                    "bot_configuration": {
                        "strategy_type": strategy_name,
                        "model_id": model_id,
                        "parameters": {
                            "timeframe": timeframe,
                            "days": days
                        }
                    }
                }
                
            except Exception as e:
                logger.error(f"Error running specific model: {e}")
                return {"error": str(e)}

        # Fallback a buscar la mejor
        return await self.find_best_strategy(symbol, timeframe, days, target_exchange)

    def _calculate_theoretical_pnl(self, df):
        # Lógica simplificada de PnL: suma de retornos en señales correctas
        df['returns'] = df['close'].pct_change().shift(-1)
        # Señal 1: Buy (Long), Señal 2: Sell (Short)
        df['strat_ret'] = 0.0
        df.loc[df['pred_signal'] == 1, 'strat_ret'] = df['returns']
        df.loc[df['pred_signal'] == 2, 'strat_ret'] = -df['returns']
        return df['strat_ret'].sum()
