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

    def _calculate_theoretical_pnl(self, df):
        # Lógica simplificada de PnL: suma de retornos en señales correctas
        df['returns'] = df['close'].pct_change().shift(-1)
        # Señal 1: Buy (Long), Señal 2: Sell (Short)
        df['strat_ret'] = 0.0
        df.loc[df['pred_signal'] == 1, 'strat_ret'] = df['returns']
        df.loc[df['pred_signal'] == 2, 'strat_ret'] = -df['returns']
        return df['strat_ret'].sum()
