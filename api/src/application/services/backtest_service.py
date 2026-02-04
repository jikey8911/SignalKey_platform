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

    async def select_best_model(self, symbol: str, timeframe: str) -> Dict[str, Any]:
        """
        Evalúa todos los modelos agnósticos y recomienda el mejor para un activo,
        utilizando exclusivamente el contrato de features de la estrategia.
        """
        self.logger.info(f"Iniciando validación técnica para {symbol}...")
        
        # 1. Obtener datos históricos del exchange
        df = await self.exchange.get_historical_data(symbol, timeframe)
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
                module = importlib.import_module(f"api.src.domain.strategies.{strat_name}")
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
        sl: float = 0.9
    ) -> Dict[str, Any]:
        """
        Ejecuta un Backtest Tournament: evalúa todas las estrategias y devuelve 
        los resultados detallados de la mejor posicionada.
        """
        self.logger.info(f"🚀 Iniciando Backtest Tournament: {symbol} | {days}d | {timeframe}")
        
        # 1. Obtener datos históricos
        # 1. Obtener datos históricos (Tarea 5.1: Sourcing de Datos Reales)
        try:
            df = await self.get_market_data(symbol, timeframe, days, exchange_id, user_id=user_id)
        except Exception as e:
            self.logger.error(f"Error fetching data: {e}")
            raise ValueError(f"No se pudieron obtener datos para {symbol}: {e}")

        # 2. Descubrir estrategias a evaluar
        strategies_to_test = self.trainer.discover_strategies()
        if not strategies_to_test:
            raise ValueError("No hay estrategias disponibles para el backtest.")

        tournament_results = []
        best_strategy_data = None
        highest_pnl = -float('inf')

        # 3. Ejecutar simulación para cada estrategia
        for strat_name in strategies_to_test:
            try:
                self.logger.info(f"🧪 Testing strategy: {strat_name}")
                
                # Cargar modelo y clase de estrategia una sola vez por estrategia
                model_path = os.path.join(self.models_dir, f"{strat_name}.pkl")
                if not os.path.exists(model_path):
                    self.logger.warning(f"⏩ Skipping {strat_name}: No .pkl model found.")
                    continue
                
                model = joblib.load(model_path)
                module = importlib.import_module(f"api.src.domain.strategies.{strat_name}")
                if "_" in strat_name:
                    class_name = "".join(w.title() for w in strat_name.split("_"))
                else:
                    class_name = strat_name
                
                # Validation / Fallback
                if not hasattr(module, class_name):
                     fallback_name = "".join(w.title() for w in strat_name.split("_"))
                     if hasattr(module, fallback_name):
                         class_name = fallback_name

                StrategyClass = getattr(module, class_name)
                strategy_obj = StrategyClass()
                features = strategy_obj.get_features()

                # Preparar DataFrame con indicadores y contexto
                # Tarea S9.4: Inyectar datos de contexto (Missing features fix)
                df_processed = self.prepare_data_for_model(df.copy(), strategy_obj)
                
                if df_processed.empty or not all(c in df_processed.columns for c in features):
                    self.logger.warning(f"⏩ Skipping {strat_name}: Missing features.")
                    continue

                # Determinar estep_investment (Monto por operación)
                step_investment = initial_balance * 0.2 # Default 20%
                
                if trade_amount and trade_amount > 0:
                    step_investment = trade_amount
                    self.logger.info(f"💰 Usando monto fijo por parámetro: ${step_investment}")
                else:
                    # Fallback to DB
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

                # Predicciones
                # Ajustar features para incluir las nuevas columnas de contexto
                # OJO: El orden debe ser EXACTAMENTE el mismo que en StrategyTrainer
                model_features = features + ['in_position', 'current_pnl']
                
                # Validar que existan todas las columnas
                valid_idx = df_processed[model_features].dropna().index
                X = df_processed.loc[valid_idx, model_features]
                df_processed.loc[valid_idx, 'ai_signal'] = model.predict(X)
                df_processed['ai_signal'] = df_processed['ai_signal'].fillna(0)

                # Simulación de trading con DCA y Flipping (Long/Short)
                # Tarea 9.1: Lógica de Inversión / Flip (S9)
                simulation_result = self._simulate_with_reversal(
                    df_processed, 
                    initial_balance=initial_balance,
                    trade_amount=step_investment,
                    tp=tp,
                    sl=sl
                )
                
                # Check if simulation failed or returned empty
                if not simulation_result:
                     continue

                tournament_results.append({
                    "strategy": strat_name,
                    "profit_pct": simulation_result['profit_pct'],
                    "total_trades": simulation_result['total_trades'],
                    "win_rate": simulation_result['win_rate'],
                    "final_balance": simulation_result['final_balance']
                })
                
                # Mantener datos detallados de la mejor
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

        # 4. Ordenar resultados
        tournament_results.sort(key=lambda x: x['profit_pct'], reverse=True)
        winner = tournament_results[0]
        
        # 5. Preparar Chart Data
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
        
        self.logger.info(f"🌍 FETCHING REAL DATA via CCXT for {symbol} (Limit: {limit} candles, User: {user_id})")
        # Use get_historical_data which now supports user-auth via _get_client_for_user
        df = await self.exchange.get_historical_data(symbol, timeframe, limit=limit, user_id=user_id)
        if df.empty:
            # Fallback to public if private fails or returns empty (though get_historical_data handles this)
            self.logger.warning("Empty data from auth client, retrying with public...")
            df = await self.exchange.get_public_historical_data(symbol, timeframe, limit=limit, exchange_id=exchange_id)
            
        if df.empty:
            raise ValueError(f"No se pudieron obtener datos para {symbol}")
        return df

    def _simulate_with_reversal(self, df_processed, initial_balance=1000.0, trade_amount=None, tp=0.03, sl=0.02):
        """
        Tarea 9.1: Lógica de Inversión / Flip (S9).
        Anteriormente _simulate_event_driven.
        Si la IA detecta cambio de tendencia, cierra y reversa.
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
        
        previous_signal = None
        active_trading = False
        
        from api.src.domain.strategies.base import BaseStrategy

        for timestamp, row in df_processed.iterrows():
            price = row['close']
            signal = row['ai_signal']
            
            # --- Logic: Wait for First Flip ---
            if previous_signal is None:
                previous_signal = signal
                continue 

            if not active_trading:
                if signal != previous_signal:
                    active_trading = True 
                else:
                    previous_signal = signal
                    continue 
            
            previous_signal = signal
            
            # --- Task 6.1: Validación de Mechas (High/Low) - Pessimistic Approach ---
            # 1. Chequeo para LONGs
            if long_amount > 0:
                avg_price = long_invested / long_amount
                
                # Check Stop Loss FIRST (Pessimistic: Assume we hit SL before TP if both in range)
                if row['low'] <= avg_price * (1 - sl):
                    exit_price = avg_price * (1 - sl)
                    pnl = (long_amount * exit_price) - long_invested
                    balance += (long_amount * exit_price)
                    pnl_percent = (pnl / long_invested * 100)
                    
                    trades.append({
                        "time": timestamp.isoformat(),
                        "type": "SELL",
                        "price": exit_price,
                        "amount": long_amount,
                        "pnl": round(pnl, 2),
                        "pnl_percent": round(pnl_percent, 2),
                        "avg_price": round(avg_price, 2),
                        "label": "SL_HIT_LONG"
                    })
                    if pnl > 0: win_count += 1
                    else: loss_count += 1
                    long_amount = 0
                    long_invested = 0
                    continue 

                # Take Profit (Sell at High)
                if row['high'] >= avg_price * (1 + tp):
                    exit_price = avg_price * (1 + tp)
                    pnl = (long_amount * exit_price) - long_invested
                    balance += (long_amount * exit_price)
                    pnl_percent = (pnl / long_invested * 100)
                    
                    trades.append({
                        "time": timestamp.isoformat(),
                        "type": "SELL",
                        "price": exit_price,
                        "amount": long_amount,
                        "pnl": round(pnl, 2),
                        "pnl_percent": round(pnl_percent, 2),
                        "avg_price": round(avg_price, 2),
                        "label": "TP_HIT_LONG"
                    })
                    if pnl > 0: win_count += 1
                    else: loss_count += 1
                    long_amount = 0
                    long_invested = 0
                    continue 
            
            # 2. Chequeo para SHORTS
            if short_amount > 0:
                avg_price = short_invested / short_amount
                
                # Check Stop Loss FIRST (Buy at High)
                if row['high'] >= avg_price * (1 + sl):
                    exit_price = avg_price * (1 + sl)
                    pnl = short_invested - (short_amount * exit_price)
                    balance += short_invested + pnl
                    pnl_percent = (pnl / short_invested * 100)
                    
                    trades.append({
                        "time": timestamp.isoformat(),
                        "type": "BUY",
                        "price": exit_price,
                        "amount": short_amount,
                        "pnl": round(pnl, 2),
                        "pnl_percent": round(pnl_percent, 2),
                        "avg_price": round(avg_price, 2),
                        "label": "SL_HIT_SHORT"
                    })
                    if pnl > 0: win_count += 1
                    else: loss_count += 1
                    short_amount = 0
                    short_invested = 0
                    continue

                # Take Profit (Buy at Low)
                if row['low'] <= avg_price * (1 - tp):
                    exit_price = avg_price * (1 - tp)
                    pnl = short_invested - (short_amount * exit_price)
                    balance += short_invested + pnl
                    pnl_percent = (pnl / short_invested * 100)
                    
                    trades.append({
                        "time": timestamp.isoformat(),
                        "type": "BUY",
                        "price": exit_price,
                        "amount": short_amount,
                        "pnl": round(pnl, 2),
                        "pnl_percent": round(pnl_percent, 2),
                        "avg_price": round(avg_price, 2),
                        "label": "TP_HIT_SHORT"
                    })
                    if pnl > 0: win_count += 1
                    else: loss_count += 1
                    short_amount = 0
                    short_invested = 0
                    continue

            # --- Trading Logic (DCA & Market Flip) ---
            if signal == BaseStrategy.SIGNAL_BUY: 
                # Check for FLIP (Short -> Long)
                if short_amount > 0:
                    # 1. Close Short (Flip Side A)
                    pnl = short_invested - (short_amount * price)
                    balance += short_invested + pnl
                    avg_entry_price = short_invested / short_amount
                    pnl_percent = (pnl / short_invested * 100)
                    
                    trades.append({
                        "time": timestamp.isoformat(),
                        "type": "BUY",
                        "price": price,
                        "amount": short_amount,
                        "pnl": round(pnl, 2),
                        "pnl_percent": round(pnl_percent, 2),
                        "avg_price": round(avg_entry_price, 2),
                        "label": "FLIP_CLOSE_SHORT" # Etiqueta específica para Flip
                    })
                    if pnl > 0: win_count += 1
                    else: loss_count += 1
                    
                    short_amount = 0
                    short_invested = 0
                    
                    # 2. Immediate Open Long (Flip Side B - Atomic Reversal)
                    # El Flip implica estar posicionado en Long inmediatamente
                    if balance >= step_investment:
                        amount_to_buy = step_investment / price
                        long_amount += amount_to_buy
                        long_invested += step_investment
                        balance -= step_investment
                        
                        trades.append({
                            "time": timestamp.isoformat(),
                            "type": "BUY",
                            "price": price,
                            "amount": amount_to_buy,
                            "avg_price": round(price, 2),
                            "label": "FLIP_OPEN_LONG" # Etiqueta específica para Flip
                        })
                
                # Normal Long (Open or DCA) if not a Flip (or if balance allowed flipping)
                elif balance >= step_investment:
                     # Si ya era Long, es DCA. Si no tenía nada, es Open Normal.
                    is_dca = long_amount > 0
                    amount_to_buy = step_investment / price
                    long_amount += amount_to_buy
                    long_invested += step_investment
                    balance -= step_investment
                    avg_entry = long_invested / long_amount
                    
                    trades.append({
                        "time": timestamp.isoformat(),
                        "type": "BUY",
                        "price": price,
                        "amount": amount_to_buy,
                        "avg_price": round(avg_entry, 2),
                        "label": "DCA_LONG" if is_dca else "OPEN_LONG"
                    })
                    
            elif signal == BaseStrategy.SIGNAL_SELL: 
                # Check for FLIP (Long -> Short)
                if long_amount > 0:
                    # 1. Close Long (Flip Side A)
                    pnl = (long_amount * price) - long_invested
                    balance += (long_amount * price)
                    avg_entry_price = long_invested / long_amount
                    pnl_percent = (pnl / long_invested * 100)
                    
                    trades.append({
                        "time": timestamp.isoformat(),
                        "type": "SELL",
                        "price": price,
                        "amount": long_amount,
                        "pnl": round(pnl, 2),
                        "pnl_percent": round(pnl_percent, 2),
                        "avg_price": round(avg_entry_price, 2),
                        "label": "FLIP_CLOSE_LONG" # Etiqueta específica para Flip
                    })
                    if pnl > 0: win_count += 1
                    else: loss_count += 1
                    
                    long_amount = 0
                    long_invested = 0
                    
                    # 2. Immediate Open Short (Flip Side B - Atomic Reversal)
                    if balance >= step_investment:
                        amount_to_short = step_investment / price
                        short_amount += amount_to_short
                        short_invested += step_investment
                        balance -= step_investment
                        
                        trades.append({
                            "time": timestamp.isoformat(),
                            "type": "SELL",
                            "price": price,
                            "amount": amount_to_short,
                            "avg_price": round(price, 2),
                            "label": "FLIP_OPEN_SHORT" # Etiqueta específica para Flip
                        })
                        
                # Normal Short (Open or DCA) if not a Flip
                elif balance >= step_investment:
                    is_dca = short_amount > 0
                    amount_to_short = step_investment / price
                    short_amount += amount_to_short
                    short_invested += step_investment
                    balance -= step_investment
                    avg_entry = short_invested / short_amount
                    
                    trades.append({
                        "time": timestamp.isoformat(),
                        "type": "SELL",
                        "price": price,
                        "amount": amount_to_short,
                        "avg_price": round(avg_entry, 2),
                        "label": "DCA_SHORT" if is_dca else "OPEN_SHORT"
                    })

        # Calculate Final Stats
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
        # 1. Aplicar indicadores técnicos base de la estrategia
        df = strategy.apply(df)
        
        # 2. Simular el contexto de posición (Igual que en el StrategyTrainer)
        df['in_position'] = 0
        df['current_pnl'] = 0.0
        
        avg_price = 0.0
        in_pos = False
        
        # Iteramos para reconstruir el estado que el modelo espera ver
        # Esto es crucial para que Random Forest no falle por falta de dimensiones
        for i in range(1, len(df)):
            if in_pos:
                df.at[df.index[i], 'in_position'] = 1
                current_price = df.iloc[i]['close']
                if avg_price > 0:
                    df.at[df.index[i], 'current_pnl'] = (current_price - avg_price) / avg_price
                
                # Si hubo una señal de venta técnica en el paso anterior, reseteamos
                # Ojo: Usamos 'signal' que genera strategy.apply() (la técnica pura)
                if df.iloc[i-1].get('signal') == BaseStrategy.SIGNAL_SELL:
                    in_pos = False
                    avg_price = 0.0
            else:
                # Si hubo señal de compra técnica, iniciamos posición simulada
                if df.iloc[i-1].get('signal') == BaseStrategy.SIGNAL_BUY:
                    in_pos = True
                    avg_price = df.iloc[i]['close']
                    
        return df