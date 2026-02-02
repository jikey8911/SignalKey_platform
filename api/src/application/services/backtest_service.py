import os
import joblib
import pandas as pd
import logging
import importlib
from typing import Dict, Any, List, Optional
from api.ml.strategy_trainer import StrategyTrainer
from api.src.domain.services.exchange_port import IExchangePort
from api.strategies.base import BaseStrategy

class BacktestService:
    """
    Servicio de Backtest de la Capa de Aplicación (sp4).
    """
    def __init__(self, exchange_adapter: IExchangePort, trainer: StrategyTrainer = None, models_dir: str = "api/data/models"):
        self.exchange = exchange_adapter
        self.trainer = trainer or StrategyTrainer()
        self.models_dir = models_dir
        self.logger = logging.getLogger("BacktestService")
        
        # Lazy load MLService to avoid circular dependency
        from api.src.application.services.ml_service import MLService
        self.ml_service = MLService(exchange_adapter=self.exchange)

    async def get_market_data(self, symbol: str, timeframe: str, days: int, exchange_id: str) -> pd.DataFrame:
        """Helper to fetch market data"""
        limit = days * 24 if timeframe == "1h" else 1000
        return await self.exchange.get_public_historical_data(symbol, timeframe, limit=limit, exchange_id=exchange_id)

    async def run_backtest(
        self, 
        symbol: str, 
        days: int = 7, 
        timeframe: str = "1h", 
        use_ai: bool = True,
        user_config: Dict = None,
        strategy: str = "auto",
        user_id: str = "default_user",
        exchange_id: str = "binance",
        model_id: Optional[str] = None,
        initial_balance: float = 10000.0,
        trade_amount: Optional[float] = None,
        tp: float = 0.03,
        sl: float = 0.02
    ) -> Dict[str, Any]:
        self.logger.info(f"🚀 Iniciando Backtest Tournament: {symbol} | {days}d | {timeframe}")
        
        try:
            df = await self.get_market_data(symbol, timeframe, days, exchange_id)
        except Exception as e:
            self.logger.error(f"Error fetching data: {e}")
            raise ValueError(f"No se pudieron obtener datos para {symbol}: {e}")

        strategies_to_test = self.trainer.discover_strategies()
        if not strategies_to_test:
            raise ValueError("No hay estrategias disponibles para el backtest.")

        tournament_results = []
        best_strategy_data = None
        highest_pnl = -float('inf')

        for strat_name in strategies_to_test:
            try:
                model_path = os.path.join(self.models_dir, f"{strat_name}.pkl")
                if not os.path.exists(model_path):
                    continue
                
                model = joblib.load(model_path)
                module = importlib.import_module(f"api.strategies.{strat_name}")
                class_name = "".join(w.title() for w in strat_name.split("_"))
                StrategyClass = getattr(module, class_name)
                strategy_obj = StrategyClass()
                features = strategy_obj.get_features()

                df_processed = strategy_obj.apply(df.copy())
                if df_processed.empty or not all(c in df_processed.columns for c in features):
                    continue

                step_investment = trade_amount if trade_amount and trade_amount > 0 else initial_balance * 0.2

                valid_idx = df_processed[features].dropna().index
                X = df_processed.loc[valid_idx, features]
                df_processed.loc[valid_idx, 'ai_signal'] = model.predict(X)
                df_processed['ai_signal'] = df_processed['ai_signal'].fillna(0)

                simulation_result = self.simulate_dca_logic(
                    df_processed, 
                    initial_balance=initial_balance,
                    trade_amount=step_investment,
                    tp=tp,
                    sl=sl
                )
                
                if not simulation_result:
                     continue

                tournament_results.append({
                    "strategy": strat_name,
                    "profit_pct": simulation_result['profit_pct'],
                    "total_trades": simulation_result['total_trades'],
                    "win_rate": simulation_result['win_rate'],
                    "final_balance": simulation_result['final_balance']
                })
                
                if simulation_result['profit_pct'] > highest_pnl:
                    highest_pnl = simulation_result['profit_pct']
                    best_strategy_data = {
                        "strategy_name": strat_name,
                        **simulation_result
                    }

            except Exception as e:
                self.logger.error(f"Error testing {strat_name}: {e}")

        if not tournament_results:
            raise ValueError(f"No se pudo completar el backtest para ninguna estrategia.")

        tournament_results.sort(key=lambda x: x['profit_pct'], reverse=True)
        winner = tournament_results[0]
        best_strat_name = winner['strategy']
        
        chart_data = []
        try:
            module = importlib.import_module(f"api.strategies.{best_strat_name}")
            class_name = "".join(w.title() for w in best_strat_name.split("_"))
            StrategyClass = getattr(module, class_name)
            best_strategy_obj = StrategyClass()
            df_best = best_strategy_obj.apply(df.copy())
            trades_map = {t['time']: t for t in best_strategy_data.get('trades', [])}
            
            for timestamp, row in df_best.iterrows():
                iso_time = timestamp.isoformat()
                trade_info = trades_map.get(iso_time)
                point = {
                    "time": int(timestamp.timestamp()),
                    "open": row['open'], "high": row['high'], "low": row['low'], "close": row['close'], "volume": row['volume']
                }
                for col in df_best.columns:
                    if col not in ['open', 'high', 'low', 'close', 'volume', 'signal', 'ai_signal']:
                        point[col] = row[col]
                if trade_info:
                    point["trade"] = {
                        "type": trade_info['type'], "price": trade_info['price'], "label": trade_info['label'],
                        "pnl": trade_info.get('pnl'), "pnl_percent": trade_info.get('pnl_percent')
                    }
                chart_data.append(point)
        except Exception as e:
            self.logger.error(f"Error preparing chart: {e}")
            for timestamp, row in df.iterrows():
                chart_data.append({"time": int(timestamp.timestamp()), "open": row['open'], "close": row['close']})
            
        return {
            "symbol": symbol, "days": days, "timeframe": timeframe, "winner": winner,
            "all_results": tournament_results, "best_strategy_details": best_strategy_data,
            "chart_data": chart_data, "market_type": exchange_id,
            "metrics": {
                "total_trades": best_strategy_data["total_trades"],
                "win_rate": best_strategy_data["win_rate"],
                "profit_pct": best_strategy_data["profit_pct"]
            },
            "trades": best_strategy_data["trades"]
        }

    def simulate_dca_logic(self, df_processed, initial_balance, trade_amount, tp, sl):
        balance = initial_balance
        step_investment = trade_amount
        long_amount = 0
        long_invested = 0
        short_amount = 0
        short_invested = 0
        trades = []
        win_count = 0
        loss_count = 0
        previous_signal = None
        active_trading = False

        for timestamp, row in df_processed.iterrows():
            price = row['close']
            signal = row['ai_signal']
            if previous_signal is None:
                previous_signal = signal
                continue 
            if not active_trading:
                if signal != previous_signal: active_trading = True 
                else: previous_signal = signal; continue 
            previous_signal = signal
            
            # Long Exit
            if long_amount > 0:
                avg_price = long_invested / long_amount
                if row['high'] >= avg_price * (1 + tp) or row['low'] <= avg_price * (1 - sl):
                    exit_price = avg_price * (1 + tp) if row['high'] >= avg_price * (1 + tp) else avg_price * (1 - sl)
                    pnl = (long_amount * exit_price) - long_invested
                    balance += (long_amount * exit_price)
                    trades.append({"time": timestamp.isoformat(), "type": "SELL", "price": exit_price, "amount": long_amount, "pnl": round(pnl, 2), "pnl_percent": round(pnl/long_invested*100, 2), "label": "TP_SL_LONG"})
                    if pnl > 0: win_count += 1
                    else: loss_count += 1
                    long_amount = 0; long_invested = 0; continue

            # Short Exit
            if short_amount > 0:
                avg_price = short_invested / short_amount
                if row['low'] <= avg_price * (1 - tp) or row['high'] >= avg_price * (1 + sl):
                    exit_price = avg_price * (1 - tp) if row['low'] <= avg_price * (1 - tp) else avg_price * (1 + sl)
                    pnl = short_invested - (short_amount * exit_price)
                    balance += short_invested + pnl
                    trades.append({"time": timestamp.isoformat(), "type": "BUY", "price": exit_price, "amount": short_amount, "pnl": round(pnl, 2), "pnl_percent": round(pnl/short_invested*100, 2), "label": "TP_SL_SHORT"})
                    if pnl > 0: win_count += 1
                    else: loss_count += 1
                    short_amount = 0; short_invested = 0; continue

            # Signals
            if signal == BaseStrategy.SIGNAL_BUY:
                if short_amount > 0:
                    pnl = short_invested - (short_amount * price)
                    balance += short_invested + pnl
                    trades.append({"time": timestamp.isoformat(), "type": "BUY", "price": price, "amount": short_amount, "pnl": round(pnl, 2), "label": "CLOSE_SHORT"})
                    if pnl > 0: win_count += 1
                    else: loss_count += 1
                    short_amount = 0; short_invested = 0
                if balance >= step_investment:
                    qty = step_investment / price
                    long_amount += qty; long_invested += step_investment; balance -= step_investment
                    trades.append({"time": timestamp.isoformat(), "type": "BUY", "price": price, "amount": qty, "label": "OPEN_DCA_LONG"})
            elif signal == BaseStrategy.SIGNAL_SELL:
                if long_amount > 0:
                    pnl = (long_amount * price) - long_invested
                    balance += (long_amount * price)
                    trades.append({"time": timestamp.isoformat(), "type": "SELL", "price": price, "amount": long_amount, "pnl": round(pnl, 2), "label": "CLOSE_LONG"})
                    if pnl > 0: win_count += 1
                    else: loss_count += 1
                    long_amount = 0; long_invested = 0
                if balance >= step_investment:
                    qty = step_investment / price
                    short_amount += qty; short_invested += step_investment; balance -= step_investment
                    trades.append({"time": timestamp.isoformat(), "type": "SELL", "price": price, "amount": qty, "label": "OPEN_DCA_SHORT"})

        final_val = balance + (long_amount * df_processed.iloc[-1]['close']) + (short_invested + (short_invested - (short_amount * df_processed.iloc[-1]['close'])) if short_amount > 0 else 0)
        return {
            "profit_pct": round(((final_val/initial_balance)-1)*100, 2),
            "total_trades": len(trades), "win_rate": round(win_count/(win_count+loss_count)*100, 2) if (win_count+loss_count)>0 else 0,
            "final_balance": round(final_val, 2), "trades": trades
        }
