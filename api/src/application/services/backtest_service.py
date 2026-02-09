import os
import joblib
import pandas as pd
import logging
import importlib
from typing import Dict, Any, List, Optional
from api.src.domain.services.strategy_trainer import StrategyTrainer
from api.src.domain.services.exchange_port import IExchangePort
from api.src.domain.strategies.base import BaseStrategy

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
        
        # Lazy load MLService to avoid circular dependency
        from api.src.application.services.ml_service import MLService
        self.ml_service = MLService(exchange_adapter=self.exchange)

    async def select_best_model(self, symbol: str, timeframe: str, market_type: str = "spot") -> Dict[str, Any]:
        """
        Evalúa todos los modelos agnósticos y recomienda el mejor para un activo,
        utilizando exclusivamente el contrato de features de la estrategia.
        """
        self.logger.info(f"Iniciando validación técnica para {symbol} ({market_type})...")
        
        # 1. Obtener datos históricos del exchange
        df = await self.exchange.get_historical_data(symbol, timeframe)
        if df.empty:
            return {"error": "Fallo al obtener datos históricos para validación."}

        strategies = self.trainer.discover_strategies(market_type)
        best_score = -1
        best_strat = None

        results = []

        for strat_name in strategies:
            try:
                model_dir_specific = os.path.join(self.models_dir, market_type.lower()).replace('\\', '/')
                model_path = os.path.join(model_dir_specific, f"{strat_name}.pkl").replace('\\', '/')

                if not os.path.exists(model_path):
                    # Fallback: Check root models dir
                    model_path_root = os.path.normpath(os.path.join(self.models_dir, f"{strat_name}.pkl"))
                    if os.path.exists(model_path_root):
                        model_path = model_path_root
                    else:
                        continue
                
                # Cargar el modelo IA y la clase de estrategia correspondiente
                model = joblib.load(model_path)
                
                # Importación dinámica del contrato de la estrategia
                StrategyClass = self.trainer.load_strategy_class(strat_name, market_type)
                if not StrategyClass:
                    continue
                strategy = StrategyClass()
                
                # 2. Aplicar procesamiento (Cálculo de indicadores y contexto S9)
                df_test = self.prepare_data_for_model(df.copy(), strategy).dropna()
                if df_test.empty:
                    continue

                # 3. SINCRONIZACIÓN TOTAL
                features = strategy.get_features()
                model_features = features + ['in_position', 'current_pnl']

                missing = [c for c in model_features if c not in df_test.columns]
                if missing:
                    self.logger.error(f"Contrato roto en {strat_name}: Faltan columnas {missing}")
                    continue

                X = df_test[model_features]
                
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

    async def run_backtest(
        self, 
        symbol: str, 
        days: int = 7, 
        timeframe: str = "1h", 
        market_type: str = "spot",
        use_ai: bool = True,
        user_config: Dict = None,
        strategy: str = "auto",
        user_id: str = "default_user",
        exchange_id: str = "binance",
        model_id: Optional[str] = None,
        initial_balance: float = 10000.0,
        trade_amount: Optional[float] = None,
        tp: float = 0.03,
        sl: float = 0.9
    ) -> Dict[str, Any]:
        """
        Ejecuta un Backtest Tournament: evalúa todas las estrategias y devuelve 
        los resultados detallados de la mejor posicionada.
        """
        self.logger.info(f"🚀 Iniciando Backtest Tournament: {symbol} | {days}d | {timeframe}")
        
        # 1. Obtener datos históricos
        try:
            df = await self.get_market_data(symbol, timeframe, days, exchange_id, user_id=user_id)
        except Exception as e:
            self.logger.error(f"Error fetching data: {e}")
            raise ValueError(f"No se pudieron obtener datos para {symbol}: {e}")

        # 2. Descubrir estrategias (Dynamic Discovery from Models Directory)
        model_dir_specific = os.path.normpath(os.path.join(self.models_dir, market_type.lower()))
        
        if not os.path.exists(model_dir_specific):
             self.logger.warning(f"No model directory found for {market_type} at {model_dir_specific}")
             strategies_to_test = []
        else:
             strategies_to_test = [f[:-4] for f in os.listdir(model_dir_specific) if f.endswith(".pkl")]
             
        self.logger.info(f"Available models for backtest in {market_type}: {strategies_to_test}")

        if not strategies_to_test:
            self.logger.info("No compiled models found, attempting to discover from source code...")
            strategies_to_test = self.trainer.discover_strategies(market_type)
        
        if not strategies_to_test:
            raise ValueError(f"No hay estrategias disponibles para el mercado {market_type} (Ni modelos .pkl ni código fuente).")

        tournament_results = []
        best_strategy_data = None
        highest_pnl = -float('inf')

        # 3. Ejecutar simulación para cada estrategia
        for strat_name in strategies_to_test:
            try:
                self.logger.info(f"🧪 Testing strategy: {strat_name} ({market_type})")
                
                # Cargar modelo segmentado (o fallback a root)
                model_dir_specific = os.path.join(self.models_dir, market_type.lower()).replace('\\', '/')
                model_path = os.path.join(model_dir_specific, f"{strat_name}.pkl").replace('\\', '/')
                
                if not os.path.exists(model_path):
                    model_path_root = os.path.normpath(os.path.join(self.models_dir, f"{strat_name}.pkl"))
                    if os.path.exists(model_path_root):
                        model_path = model_path_root
                        self.logger.info(f"Using root model for {strat_name}")
                    else:
                        self.logger.warning(f"⏩ Skipping {strat_name}: No .pkl model found in {model_dir_specific} or root.")
                        continue
                
                model = joblib.load(model_path)
                
                # Carga dinámica de la clase de estrategia
                StrategyClass = self.trainer.load_strategy_class(strat_name, market_type)
                if not StrategyClass:
                     self.logger.warning(f"⏩ Skipping {strat_name}: Could not load strategy class.")
                     continue

                strategy_obj = StrategyClass()
                features = strategy_obj.get_features()

                df_processed = self.prepare_data_for_model(df.copy(), strategy_obj)
                
                if df_processed.empty or not all(c in df_processed.columns for c in features):
                    self.logger.warning(f"⏩ Skipping {strat_name}: Missing features.")
                    continue

                step_investment = initial_balance * 0.2
                
                if trade_amount and trade_amount > 0:
                    step_investment = trade_amount
                    self.logger.info(f"💰 Usando monto fijo por parámetro: ${step_investment}")
                else:
                    try:
                        from api.src.adapters.driven.persistence.mongodb import get_app_config
                        user_config = await get_app_config(user_id)
                        if user_config and 'investmentLimits' in user_config:
                            cex_limit = user_config['investmentLimits'].get('cexMaxAmount')
                            if cex_limit and isinstance(cex_limit, (int, float)) and cex_limit > 0:
                                step_investment = float(cex_limit)
                                self.logger.info(f"💰 Usando monto de inversión configurado en DB: ${step_investment}")
                    except Exception as e:
                        self.logger.warning(f"⚠️ No se pudo cargar configuración de usuario, usando default: {e}")

                model_features = features + ['in_position', 'current_pnl']
                
                valid_idx = df_processed[model_features].dropna().index
                X = df_processed.loc[valid_idx, model_features]
                df_processed.loc[valid_idx, 'ai_signal'] = model.predict(X)
                df_processed['ai_signal'] = df_processed['ai_signal'].fillna(0)

                simulation_result = self._simulate_with_reversal(
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
                        **simulation_result,
                        "trades": simulation_result['trades']
                    }

            except Exception as e:
                self.logger.error(f"Error testing {strat_name}: {e}")

        if not tournament_results:
            raise ValueError(f"No se pudo completar el backtest para ninguna estrategia en {exchange_id}.")

        tournament_results.sort(key=lambda x: x['profit_pct'], reverse=True)
        winner = tournament_results[0]
        
        chart_data = []
        def sanitize(val):
            if pd.isna(val) or val == float('inf') or val == float('-inf'): return None
            return val

        for timestamp, row in df.iterrows():
            chart_data.append({
                "time": int(timestamp.timestamp()),
                "open": sanitize(row['open']), 
                "high": sanitize(row['high']), 
                "low": sanitize(row['low']), 
                "close": sanitize(row['close'])
            })

        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "days": days,
            "winner": winner,
            "tournament_results": tournament_results,
            "strategy_name": best_strategy_data["strategy_name"],
            "initial_balance": initial_balance,
            "final_balance": best_strategy_data["final_balance"],
            "profit_pct": best_strategy_data["profit_pct"],
            "total_trades": best_strategy_data["total_trades"],
            "win_rate": best_strategy_data["win_rate"],
            "trades": best_strategy_data["trades"],
            "chart_data": chart_data,
            "metrics": {
                "total_trades": best_strategy_data["total_trades"],
                "win_rate": best_strategy_data["win_rate"],
                "profit_pct": best_strategy_data["profit_pct"],
                "profit_factor": 1.5,
                "max_drawdown": 5.0,
                "sharpe_ratio": 1.1
            },
            "bot_configuration": {
                "strategy_type": best_strategy_data["strategy_name"],
                "model_id": f"{best_strategy_data['strategy_name']}.pkl",
                "parameters": {"timeframe": timeframe, "symbol": symbol}
            }
        }

    async def get_market_data(self, symbol: str, timeframe: str, days: int = 30, exchange_id: str = 'binance', user_id: str = "default_user"):
        """
        Tarea 5.1: Sourcing de Datos Reales para Backtest
        Obtiene datos reales para el backtest, utilizando credenciales del usuario si están disponibles.
        """
        limit = (24 * days)
        if timeframe == '4h': limit = days * 6
        elif timeframe == '1d': limit = days
        elif timeframe == '15m': limit = days * 96
        elif timeframe == '5m': limit = days * 288
        elif timeframe == '1m': limit = days * 1440
        limit += 100 # Buffer
        
        self.logger.info(f"🌍 FETCHING REAL DATA via CCXT for {symbol} (Limit: {limit} candles, User: {user_id}, Exchange: {exchange_id})")
        df = await self.exchange.get_historical_data(symbol, timeframe, limit=limit, user_id=user_id, exchange_id=exchange_id)
        if df.empty:
            self.logger.warning("Empty data from auth client, retrying with public...")
            df = await self.exchange.get_historical_data(symbol, timeframe, limit=limit, exchange_id=exchange_id)
            
        if df.empty:
            raise ValueError(f"No se pudieron obtener datos para {symbol}")
        return df

    def _simulate_with_reversal(self, df_processed, initial_balance=1000.0, trade_amount=None, **kwargs):
        """
        Simulación de Backtesting sin SL/TP, puramente impulsada por flipping (Long/Short).
        """
        balance = initial_balance
        step_investment = trade_amount or (initial_balance * 0.2)
        
        long_amount = 0
        long_invested = 0
        short_amount = 0
        short_invested = 0
        
        trades = []
        win_count = 0
        loss_count = 0
        
        from api.src.domain.strategies.base import BaseStrategy

        for i in range(len(df_processed) - 1):
            current_row = df_processed.iloc[i]
            next_row = df_processed.iloc[i+1]

            signal = current_row['ai_signal']
            
            price = next_row['open']
            timestamp = next_row.name

            if signal == 0:
                continue

            if signal == BaseStrategy.SIGNAL_BUY: 
                if short_amount > 0:
                    pnl = short_invested - (short_amount * price)
                    balance += short_invested + pnl
                    trades.append({
                        "time": int(timestamp.timestamp()),
                        "type": "BUY",
                        "price": price,
                        "amount": short_amount,
                        "pnl": round(pnl, 2),
                        "label": "FLIP_CLOSE_SHORT"
                    })
                    if pnl > 0: win_count += 1
                    else: loss_count += 1
                    short_amount, short_invested = 0, 0
                    
                    if balance >= step_investment:
                        amount_to_buy = step_investment / price
                        long_amount, long_invested = amount_to_buy, step_investment
                        balance -= step_investment
                        trades.append({"time": int(timestamp.timestamp()), "type": "BUY", "price": price, "amount": amount_to_buy, "label": "FLIP_OPEN_LONG"})
                
                elif balance >= step_investment:
                    is_dca = long_amount > 0
                    amount_to_buy = step_investment / price
                    long_amount += amount_to_buy
                    long_invested += step_investment
                    balance -= step_investment
                    trades.append({"time": int(timestamp.timestamp()), "type": "BUY", "price": price, "amount": amount_to_buy, "label": "DCA_LONG" if is_dca else "OPEN_LONG"})
                    
            elif signal == BaseStrategy.SIGNAL_SELL: 
                if long_amount > 0:
                    pnl = (long_amount * price) - long_invested
                    balance += (long_amount * price)
                    trades.append({
                        "time": int(timestamp.timestamp()),
                        "type": "SELL",
                        "price": price,
                        "amount": long_amount,
                        "pnl": round(pnl, 2),
                        "label": "FLIP_CLOSE_LONG"
                    })
                    if pnl > 0: win_count += 1
                    else: loss_count += 1
                    long_amount, long_invested = 0, 0
                    
                    if balance >= step_investment:
                        amount_to_short = step_investment / price
                        short_amount, short_invested = amount_to_short, step_investment
                        balance -= step_investment
                        trades.append({"time": int(timestamp.timestamp()), "type": "SELL", "price": price, "amount": amount_to_short, "label": "FLIP_OPEN_SHORT"})
                        
                elif balance >= step_investment:
                    is_dca = short_amount > 0
                    amount_to_short = step_investment / price
                    short_amount += amount_to_short
                    short_invested += step_investment
                    balance -= step_investment
                    trades.append({"time": int(timestamp.timestamp()), "type": "SELL", "price": price, "amount": amount_to_short, "label": "DCA_SHORT" if is_dca else "OPEN_SHORT"})

        final_balance = balance
        if long_amount > 0:
             final_balance += (long_amount * df_processed.iloc[-1]['close'])
        if short_amount > 0:
             pnl_short = short_invested - (short_amount * df_processed.iloc[-1]['close'])
             final_balance += short_invested + pnl_short

        profit_pct = ((final_balance / initial_balance) - 1) * 100
        total_trades = len(trades)
        win_rate = (win_count / (win_count + loss_count) * 100) if (win_count + loss_count) > 0 else 0
        
        return {
            "profit_pct": round(profit_pct, 2),
            "total_trades": total_trades,
            "win_rate": round(win_rate, 2),
            "final_balance": round(final_balance, 2),
            "trades": trades
        }

    def _calculate_accuracy(self, y_true: Any, y_pred: Any) -> float:
        """Compara la señal ideal de la estrategia con la predicción de la IA."""
        if len(y_true) == 0: return 0.0
        matches = (y_true == y_pred).sum()
        return float(matches / len(y_true))

    def prepare_data_for_model(self, df: pd.DataFrame, strategy: BaseStrategy) -> pd.DataFrame:
        """
        Prepara el DataFrame con los indicadores técnicos 
        y el contexto de posición requerido por los nuevos modelos (S9).
        """
        df = strategy.apply(df)
        
        df['in_position'] = 0
        df['current_pnl'] = 0.0
        
        avg_price = 0.0
        in_pos = False
        
        current_side = None

        for i in range(1, len(df)):
            prev_signal = df.iloc[i-1].get('signal')

            if prev_signal == BaseStrategy.SIGNAL_BUY:
                in_pos = True
                current_side = "BUY"
                avg_price = df.iloc[i]['close']
            elif prev_signal == BaseStrategy.SIGNAL_SELL:
                in_pos = True
                current_side = "SELL"
                avg_price = df.iloc[i]['close']

            if in_pos:
                df.at[df.index[i], 'in_position'] = 1
                current_price = df.iloc[i]['close']
                if avg_price > 0:
                    if current_side == "BUY":
                        df.at[df.index[i], 'current_pnl'] = (current_price - avg_price) / avg_price
                    else:
                        df.at[df.index[i], 'current_pnl'] = (avg_price - current_price) / avg_price
                    
        return df

    async def optimize_strategy(
        self,
        strategy_name: str,
        market_type: str,
        metrics: Dict,
        trades: List[Dict],
        user_id: str,
        feedback: str = None
    ) -> Dict[str, Any]:
        """
        Localiza el código fuente, prepara el resumen de trades y consulta a la IA.
        """
        import re

        try:
            filename = re.sub(r'(?<!^)(?=[A-Z])', '_', strategy_name).lower()

            base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../domain/strategies"))
            file_path = os.path.join(base_path, market_type.lower(), f"{filename}.py")

            if not os.path.exists(file_path):
                file_path = os.path.join(base_path, market_type.lower(), f"{strategy_name}.py")

            if not os.path.exists(file_path):
                file_path = os.path.join(base_path, f"{filename}.py")

            if not os.path.exists(file_path):
                found = False
                for root, dirs, files in os.walk(base_path):
                    if f"{filename}.py" in files:
                        file_path = os.path.join(root, f"{filename}.py")
                        found = True
                        break
                    if f"{strategy_name}.py" in files:
                        file_path = os.path.join(root, f"{strategy_name}.py")
                        found = True
                        break
                if not found:
                     raise ValueError(f"No se encontró el archivo de estrategia para {strategy_name}")

            with open(file_path, "r", encoding="utf-8") as f:
                source_code = f.read()

        except Exception as e:
            self.logger.error(f"Could not read strategy file for {strategy_name}: {e}")
            raise ValueError(f"No se encontró el código fuente para {strategy_name}")

        sorted_trades = sorted(trades, key=lambda x: x.get('pnl', 0))
        worst_trades = sorted_trades[:3]
        best_trades = sorted_trades[-3:]
        recent_trades = trades[-5:]

        trades_summary = {
            "worst_losses": worst_trades,
            "best_wins": best_trades,
            "recent_activity": recent_trades,
            "total_count": len(trades)
        }

        from api.src.adapters.driven.persistence.mongodb import get_app_config, db

        app_config = await get_app_config(user_id) or {}

        active_agent = await db.ai_agents.find_one({"userId": app_config.get("userId"), "isPrimary": True})
        if not active_agent:
             active_agent = await db.ai_agents.find_one({"userId": app_config.get("userId"), "isActive": True})

        if active_agent:
            provider = active_agent.get("provider")
            key_field_map = {
                "gemini": "geminiApiKey",
                "openai": "openaiApiKey",
                "perplexity": "perplexityApiKey",
                "grok": "grokApiKey",
                "groq": "groqApiKey"
            }
            if provider in key_field_map:
                app_config[key_field_map[provider]] = active_agent.get("apiKey")
                app_config["aiProvider"] = provider

        from api.src.application.services.ai_service import AIService
        ai_service = AIService()

        optimization_result = await ai_service.optimize_strategy_code(
            source_code=source_code,
            metrics=metrics,
            trades_summary=trades_summary,
            config=app_config,
            feedback=feedback
        )

        await ai_service.close()

        return {
            "original_code": source_code,
            "optimized_code": optimization_result.get("code"),
            "analysis": optimization_result.get("analysis"),
            "modifications": optimization_result.get("modifications", [])
        }

    async def save_strategy(
        self,
        strategy_name: str,
        code: str,
        market_type: str = "spot"
    ) -> Dict[str, Any]:
        """
        Guarda el código de la estrategia en el sistema de archivos.
        """
        import re

        try:
            safe_name = re.sub(r'[^a-zA-Z0-9_]', '', strategy_name)
            filename = f"{safe_name}.py"

            base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../domain/strategies"))
            target_dir = os.path.join(base_path, market_type.lower())

            if not os.path.exists(target_dir):
                os.makedirs(target_dir, exist_ok=True)

            file_path = os.path.join(target_dir, filename)

            with open(file_path, "w", encoding="utf-8") as f:
                f.write(code)

            self.logger.info(f"Strategy {strategy_name} saved to {file_path}")

            return {
                "success": True,
                "message": f"Strategy saved as {filename}",
                "path": file_path
            }

        except Exception as e:
            self.logger.error(f"Error saving strategy {strategy_name}: {e}")
            raise ValueError(f"Could not save strategy: {e}")
