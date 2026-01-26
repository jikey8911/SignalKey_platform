# import ccxt.async_support as ccxt # Removed to use adapter
import pandas as pd
import os
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
import numpy as np

from api.src.application.services.ml_service import MLService
from api.src.adapters.driven.persistence.mongodb import db
from api.src.adapters.driven.exchange.ccxt_adapter import ccxt_service
from api.strategies.rsi_reversion import RSIReversion
from api.strategies.trend_ema import TrendEMA
from api.strategies.volatility_breakout import VolatilityBreakout

logger = logging.getLogger(__name__)

from api.strategies import load_strategies

class BacktestService:
    def __init__(self):
        # self.exchange removed to avoid unclosed sessions
        self.ml_service = MLService()
        self.strategies, _ = load_strategies()

    async def run_backtest(
        self, 
        user_id: str,
        symbol: str, 
        days: int = 7, 
        timeframe: str = '1h',
        use_ai: bool = True, # Ignored, always uses Model now as per plan
        user_config: Dict[str, Any] = None,
        strategy: str = "auto", # 'auto' implies neural selection
        initial_balance: Optional[float] = None,
        exchange_id: str = "binance"
    ) -> Dict[str, Any]:
        """
        Ejecuta backtest usando EXCLUSIVAMENTE el modelo ML entrenado (Meta-Selector).
        """
        logger.info(f"🚀 Iniciando Backtest ML para {symbol} ({days}d {timeframe})")
        
        # 1. Configuración Inicial
        if initial_balance is None:
            initial_balance = await self._get_user_virtual_balance(user_id)
            
        balance = initial_balance
        virtual_balance = initial_balance # USAR este para trading
        
        # 2. Obtener Datos Históricos
        # Note: In production use ccxt_service for consistency, but for this refactor we keep direct ccxt call or use service passed in?
        # The file imported ccxt directly before. I'll stick to ccxt but async to be cleaner if possible, or sync. 
        # Previous code used sync ccxt.binance(). 
        # Making it async compatible inside the method for safety.
        
        try:
            logger.info(f"⏳ Fetching historical data for {symbol}...")
            # Utilizar el adaptador CCXT que maneja la sesión con ThreadedResolver (Fix DNS Windows)
            ohlcv = await ccxt_service.get_historical_ohlcv(
                symbol=symbol,
                exchange_id=exchange_id,
                timeframe=timeframe,
                days_back=days
            )
            
            if not ohlcv:
                logger.error(f"No se pudieron obtener datos históricos para {symbol} en {exchange_id}")
                return {"error": f"Failed to fetch historical data for {symbol} on {exchange_id}"}
            
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            logger.info(f"✅ Data loaded: {len(df)} candles. Range: {df['timestamp'].iloc[0]} - {df['timestamp'].iloc[-1]}")
            
            # 3. Predicciones en Lote (Meta-Selector)
            candles = df.to_dict('records')
            logger.info(f"🧠 Generating ML predictions for {len(candles)} candles...")
            model_predictions = self.ml_service.predict_batch(symbol, timeframe, candles)
            logger.info(f"✅ Predictions generated: {len(model_predictions) if model_predictions else 0}")
            
            if not model_predictions:
                 logger.warning("No predictions returned from MLService")
                 return {"error": "Model failed to generate predictions"}

            # 4. Simulación de Trading
            trades = []
            chart_data = [] # { time, open, close, signal, equity }
            
            position = 0 # 0 or amount of asset
            entry_price = 0
            fee = 0.001
            
            # Map predictions to index
            # Results are aligned with candles.
            
            for i in range(len(candles)):
                candle = candles[i]
                current_price = candle['close']
                timestamp = candle['timestamp'].timestamp() # Unix int for frontend charts usually
                
                # Default chart point
                point = {
                    "time": int(timestamp),
                    "open": candle['open'],
                    "high": candle['high'],
                    "low": candle['low'],
                    "close": candle['close'],
                    "volume": candle['volume'],
                    "signal": None,
                    "equity": virtual_balance + (position * current_price if position > 0 else 0)
                }
                
                # Logic Execution
                # Need context for algos (approx 100 candles max)
                start_idx = max(0, i - 100)
                window_slice = df.iloc[start_idx : i + 1] # Include current
                
                prediction = model_predictions[i]
                pred_strategy = prediction['strategy']
                action = prediction['action']
                confidence = prediction['confidence']
                
                executed_signal = None
                
                if action == "CHECK_SIGNAL" and pred_strategy in self.strategies:
                    # Execute Algos based on Model Suggestion
                    algo = self.strategies[pred_strategy]
                    try:
                        res = algo.get_signal(window_slice)
                        algo_signal = res.get('signal') # 'buy', 'sell', 'hold'
                        
                        # EXECUTE BUY
                        if algo_signal == 'buy' and position == 0 and virtual_balance > 0:
                            # Buy logic
                            amount_to_spend = virtual_balance * 0.98 # Leave dust
                            coin_amount = amount_to_spend / current_price
                            cost = coin_amount * current_price
                            
                            virtual_balance -= (cost + (cost * fee))
                            position = coin_amount
                            entry_price = current_price
                            
                            executed_signal = "BUY"
                            trades.append({
                                "type": "BUY",
                                "price": current_price,
                                "time": candle['timestamp'].isoformat(),
                                "strategy": pred_strategy,
                                "confidence": confidence,
                                "balance_after": virtual_balance
                            })
                            point["signal"] = "BUY"
                            
                        # EXECUTE SELL
                        elif algo_signal == 'sell' and position > 0:
                            # Sell logic
                            revenue = position * current_price
                            fee_cost = revenue * fee
                            total_return = revenue - fee_cost
                            
                            pnl_pct = ((current_price - entry_price) / entry_price) * 100
                            virtual_balance += total_return
                            position = 0
                            
                            executed_signal = "SELL"
                            trades.append({
                                "type": "SELL",
                                "price": current_price,
                                "time": candle['timestamp'].isoformat(),
                                "strategy": pred_strategy,
                                "pnl": pnl_pct,
                                "confidence": confidence,
                                "balance_after": virtual_balance
                            })
                            point["signal"] = "SELL"
                            
                    except Exception as e:
                        logger.debug(f"Error executing algo {pred_strategy}: {e}")
                
                # Update Point Equity (Mark to Market)
                current_equity = virtual_balance + (position * current_price if position > 0 else 0)
                point["equity"] = current_equity
                
                chart_data.append(point)
            
            # Close final position
            if position > 0:
                final_price = candles[-1]['close']
                revenue = position * final_price
                virtual_balance += revenue
                position = 0
                trades.append({
                    "type": "SELL",
                    "price": final_price,
                    "time": candles[-1]['timestamp'].isoformat(),
                    "reason": "End of backtest",
                    "pnl": 0.0
                })

            # 5. Métricas Finales
            final_balance = virtual_balance
            total_profit = final_balance - initial_balance
            profit_pct = (total_profit / initial_balance) * 100
            
            winning_trades = [t for t in trades if t.get('pnl', 0) > 0]
            losing_trades = [t for t in trades if t.get('pnl', 0) <= 0 and t['type'] == 'SELL']
            buy_trades = [t for t in trades if t['type'] == 'BUY']
            
            win_rate = (len(winning_trades) / len(buy_trades) * 100) if buy_trades else 0
            
            # Calculate Max Drawdown
            peaks = pd.Series([p['equity'] for p in chart_data]).cummax()
            drawdowns = (pd.Series([p['equity'] for p in chart_data]) - peaks) / peaks * 100
            max_drawdown = drawdowns.min() # Negative value
            
            # 6. Bot Configuration
            bot_config = {
                "strategy_type": "meta-lstm-v1",
                "symbol": symbol,
                "timeframe": timeframe,
                "model_id": f"{symbol.replace('/', '_')}_{timeframe}",
            }
            
            # Verify if specific model exists, else fallback to GLOBAL for config
            safe_symbol = symbol.replace('/', '_')
            specific_model = f"{safe_symbol}_{timeframe}"
            specific_path = f"{self.ml_service.models_dir}/{specific_model}_lstm.pth"
            
            final_model_id = specific_model
            if not os.path.exists(specific_path):
                global_model = f"GLOBAL_{timeframe}"
                global_path = f"{self.ml_service.models_dir}/{global_model}_lstm.pth"
                if os.path.exists(global_path):
                    final_model_id = global_model
            
            bot_config["model_id"] = final_model_id
            
            # Continue with rest of config...
            bot_config.update({
                "parameters": {
                    "use_neural_selection": True,
                    "min_confidence": 0.65, # Configurable
                    "leverage": 1,
                    "initial_balance": initial_balance
                },
                "recommended_strategies": list(set([t['strategy'] for t in trades if 'strategy' in t]))
            })
            
            logger.info(f"🏁 Backtest completed. Trades: {len(trades)}, Profit: {profit_pct:.2f}%")
            return {
                "status": "success",
                "strategy_name": "Meta-LSTM Neural Selector",
                "metrics": {
                    "initial_balance": initial_balance,
                    "final_balance": final_balance,
                    "profit_pct": profit_pct,
                    "total_trades": len(buy_trades),
                    "win_rate": win_rate,
                    "max_drawdown": abs(max_drawdown),
                    "sharpe_ratio": 0.0 # TODO: implement
                },
                "trades": trades,
                "chart_data": chart_data, # Data for frontend graph
                "bot_configuration": bot_config
            }

        except Exception as e:
            logger.error(f"Error in backtest run: {e}")
            import traceback
            traceback.print_exc()
            return {"error": str(e)}

    async def _get_user_virtual_balance(self, user_id: str, market_type: str = "CEX", asset: str = "USDT") -> float:
        try:
            # Simple wrapper to avoid circular dependency issues or reuse logic
            # For now simplified:
            return 10000.0
        except:
            return 10000.0


