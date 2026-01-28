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
        use_ai: bool = True,
        user_config: Dict[str, Any] = None,
        strategy: str = "auto",
        initial_balance: Optional[float] = None,
        exchange_id: str = "binance",
        model_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Ejecuta backtest con estrategia única seleccionada por ML.
        Soporta posiciones LONG y SHORT con compras/ventas acumulativas.
        """
        logger.info(f"🚀 Iniciando Backtest ML para {symbol} ({days}d {timeframe})")
        
        try:
            # 1. Configuración Inicial
            if initial_balance is None:
                initial_balance = await self._get_user_virtual_balance(user_id)
            
            virtual_balance = initial_balance
            
            # 2. Obtener Datos Históricos
            logger.info(f"⏳ Fetching historical data for {symbol}...")
            ohlcv = await ccxt_service.get_historical_ohlcv(
                symbol=symbol,
                exchange_id=exchange_id,
                timeframe=timeframe,
                days_back=days
            )
            
            if not ohlcv:
                logger.error(f"No se pudieron obtener datos históricos para {symbol}")
                return {"error": f"Failed to fetch historical data for {symbol}"}
            
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            candles = df.to_dict('records')
            logger.info(f"✅ Data loaded: {len(df)} candles")
            
            # 3. Seleccionar Estrategia Óptima con ML
            logger.info(f"🧠 Selecting optimal strategy using ML...")
            strategy_selection = self.ml_service.select_best_strategy(
                symbol, 
                timeframe, 
                candles, 
                model_name=model_id
            )
            
            selected_strategy_name = strategy_selection['strategy_name']
            model_used = strategy_selection['model_used']
            ml_confidence = strategy_selection['confidence']
            
            if selected_strategy_name == "HOLD" or selected_strategy_name not in self.strategies:
                logger.warning(f"No profitable strategy found. Selected: {selected_strategy_name}")
                return {"error": "No profitable strategy found by ML model"}
            
            selected_strategy = self.strategies[selected_strategy_name]
            logger.info(f"✅ Selected strategy: {selected_strategy_name} (confidence: {ml_confidence:.2f})")
            logger.info(f"📊 Model used: {model_used}")
            
            # 4. Parámetros TP/SL (Default)
            # optimize_trade_parameters legacy call removed
            take_profit_pct = 2.0
            stop_loss_pct = 1.0
            logger.info(f"✅ Using default TP: {take_profit_pct}%, SL: {stop_loss_pct}%")
            
            # 5. Ejecutar Backtest con Estrategia Única
            logger.info(f"📈 Running backtest with {selected_strategy_name}...")
            
            # Variables de estado para posiciones LONG y SHORT
            long_positions = []
            total_long = 0
            avg_long_price = 0
            
            short_positions = []
            total_short = 0
            avg_short_price = 0
            
            trades = []
            chart_data = []
            fee = 0.001
            
            investment_limits = user_config.get("investmentLimits", {}) if user_config else {}
            max_amount_cfg = investment_limits.get("cexMaxAmount", 100.0)
            
            # Loop principal de trading
            for i in range(len(candles)):
                candle = candles[i]
                current_price = candle['close']
                timestamp = candle['timestamp'].timestamp()
                
                # Calcular PnL no realizado
                unrealized_pnl_pct = 0
                if total_long > 0:
                    unrealized_pnl_pct = ((current_price - avg_long_price) / avg_long_price) * 100
                elif total_short > 0:
                    unrealized_pnl_pct = ((avg_short_price - current_price) / avg_short_price) * 100
                
                # Calcular Break-Even Price (Entry * (1+fee)/(1-fee))
                avg_entry = avg_long_price if total_long > 0 else (avg_short_price if total_short > 0 else 0)
                be_price = 0
                if avg_entry > 0:
                    be_price = avg_entry * (1 + fee) / (1 - fee)

                # Crear contexto de posición para la estrategia
                position_context = {
                    'has_position': total_long > 0 or total_short > 0,
                    'position_type': 'LONG' if total_long > 0 else ('SHORT' if total_short > 0 else None),
                    'avg_entry_price': avg_entry,
                    'current_price': current_price,
                    'unrealized_pnl_pct': unrealized_pnl_pct,
                    'position_count': len(long_positions) if total_long > 0 else len(short_positions),
                    'break_even_price': be_price
                }
                
                # Obtener señal de la estrategia CON CONTEXTO
                window_slice = df.iloc[max(0, i - 100) : i + 1]
                try:
                    signal_result = selected_strategy.get_signal(window_slice, position_context)
                    algo_signal = signal_result.get('signal', 'hold')
                except Exception as e:
                    logger.debug(f"Error getting signal: {e}")
                    algo_signal = 'hold'
                
                # Verificar TP/SL para posición LONG
                if total_long > 0:
                    tp_price = avg_long_price * (1 + take_profit_pct / 100)
                    sl_price = avg_long_price * (1 - stop_loss_pct / 100)
                    
                    if current_price >= tp_price:
                        algo_signal = 'sell'
                    elif current_price <= sl_price:
                        algo_signal = 'sell'
                
                # Verificar TP/SL para posición SHORT
                if total_short > 0:
                    tp_price = avg_short_price * (1 - take_profit_pct / 100)  # TP es MENOR
                    sl_price = avg_short_price * (1 + stop_loss_pct / 100)  # SL es MAYOR
                    
                    if current_price <= tp_price:
                        algo_signal = 'buy'
                    elif current_price >= sl_price:
                        algo_signal = 'buy'
                
                # SEÑAL BUY
                if algo_signal == 'buy':
                    if total_short > 0:
                        # CERRAR POSICIÓN SHORT
                        cost = total_short * current_price
                        fee_cost = cost * fee
                        pnl = (avg_short_price - current_price) * total_short
                        virtual_balance -= (cost + fee_cost - pnl)
                        
                        trades.append({
                            "type": "BUY_TO_CLOSE",
                            "position_type": "SHORT",
                            "price": current_price,
                            "amount": total_short,
                            "time": candle['timestamp'].isoformat(),
                            "avg_entry": avg_short_price,
                            "pnl": pnl,
                            "pnl_pct": (pnl / (avg_short_price * total_short)) * 100,
                            "balance_after": virtual_balance
                        })
                        
                        short_positions = []
                        total_short = 0
                        avg_short_price = 0
                        
                    elif virtual_balance > 0:
                        # ABRIR O ACUMULAR POSICIÓN LONG
                        amount_to_spend = min(float(max_amount_cfg), virtual_balance * 0.98)
                        coin_amount = amount_to_spend / current_price
                        fee_cost = amount_to_spend * fee
                        
                        virtual_balance -= (amount_to_spend + fee_cost)
                        
                        long_positions.append({
                            'price': current_price,
                            'amount': coin_amount,
                            'cost': amount_to_spend
                        })
                        
                        total_long += coin_amount
                        total_cost = sum(p['cost'] for p in long_positions)
                        avg_long_price = total_cost / total_long
                        
                        trades.append({
                            "type": "BUY",
                            "position_type": "LONG",
                            "price": current_price,
                            "amount": coin_amount,
                            "time": candle['timestamp'].isoformat(),
                            "position_number": len(long_positions),
                            "avg_entry": avg_long_price,
                            "total_position": total_long,
                            "balance_after": virtual_balance
                        })
                
                # SEÑAL SELL
                elif algo_signal == 'sell':
                    if total_long > 0:
                        # CERRAR POSICIÓN LONG
                        revenue = total_long * current_price
                        fee_cost = revenue * fee
                        total_return = revenue - fee_cost
                        pnl = revenue - sum(p['cost'] for p in long_positions)
                        
                        virtual_balance += total_return
                        
                        trades.append({
                            "type": "SELL_TO_CLOSE",
                            "position_type": "LONG",
                            "price": current_price,
                            "amount": total_long,
                            "time": candle['timestamp'].isoformat(),
                            "avg_entry": avg_long_price,
                            "pnl": pnl,
                            "pnl_pct": (pnl / sum(p['cost'] for p in long_positions)) * 100,
                            "balance_after": virtual_balance
                        })
                        
                        long_positions = []
                        total_long = 0
                        avg_long_price = 0
                        
                    elif virtual_balance > 0:
                        # ABRIR O ACUMULAR POSICIÓN SHORT
                        amount_to_short = min(float(max_amount_cfg), virtual_balance * 0.98)
                        coin_amount = amount_to_short / current_price
                        fee_cost = amount_to_short * fee
                        
                        # En short, recibimos el dinero (pero lo reservamos)
                        virtual_balance += (amount_to_short - fee_cost)
                        
                        short_positions.append({
                            'price': current_price,
                            'amount': coin_amount,
                            'value': amount_to_short
                        })
                        
                        total_short += coin_amount
                        total_value = sum(p['value'] for p in short_positions)
                        avg_short_price = total_value / total_short
                        
                        trades.append({
                            "type": "SELL_SHORT",
                            "position_type": "SHORT",
                            "price": current_price,
                            "amount": coin_amount,
                            "time": candle['timestamp'].isoformat(),
                            "position_number": len(short_positions),
                            "avg_entry": avg_short_price,
                            "total_position": total_short,
                            "balance_after": virtual_balance
                        })
                
                # Chart data point
                current_equity = virtual_balance
                if total_long > 0:
                    current_equity += total_long * current_price
                if total_short > 0:
                    current_equity -= total_short * current_price
                
                chart_data.append({
                    "time": int(timestamp),
                    "open": candle['open'],
                    "high": candle['high'],
                    "low": candle['low'],
                    "close": candle['close'],
                    "volume": candle['volume'],
                    "signal": algo_signal if algo_signal != 'hold' else None,
                    "equity": current_equity
                })
            
            # Cerrar posiciones finales
            final_price = candles[-1]['close']
            
            if total_long > 0:
                revenue = total_long * final_price
                virtual_balance += (revenue - revenue * fee)
                trades.append({
                    "type": "SELL_TO_CLOSE",
                    "position_type": "LONG",
                    "price": final_price,
                    "amount": total_long,
                    "time": candles[-1]['timestamp'].isoformat(),
                    "reason": "End of backtest"
                })
            
            if total_short > 0:
                cost = total_short * final_price
                virtual_balance -= (cost + cost * fee)
                trades.append({
                    "type": "BUY_TO_CLOSE",
                    "position_type": "SHORT",
                    "price": final_price,
                    "amount": total_short,
                    "time": candles[-1]['timestamp'].isoformat(),
                    "reason": "End of backtest"
                })
            
            # 6. Calcular Métricas
            final_balance = virtual_balance
            profit_pct = ((final_balance - initial_balance) / initial_balance) * 100
            
            close_trades = [t for t in trades if 'CLOSE' in t['type']]
            long_trades = [t for t in trades if t.get('position_type') == 'LONG' and 'CLOSE' in t['type']]
            short_trades = [t for t in trades if t.get('position_type') == 'SHORT' and 'CLOSE' in t['type']]
            
            winning_trades = [t for t in close_trades if t.get('pnl', 0) > 0]
            win_rate = (len(winning_trades) / len(close_trades) * 100) if close_trades else 0
            
            # Max drawdown
            equity_series = pd.Series([p['equity'] for p in chart_data])
            peaks = equity_series.cummax()
            drawdowns = (equity_series - peaks) / peaks * 100
            max_drawdown = drawdowns.min()
            
            # Sharpe Ratio
            returns_series = equity_series.pct_change().dropna()
            if len(returns_series) > 0 and returns_series.std() > 0:
                sharpe_ratio = (returns_series.mean() / returns_series.std()) * (252 ** 0.5) 
            else:
                sharpe_ratio = 0.0

            # Signal Distribution (from chart data)
            signals_list = [d['signal'] for d in chart_data if d['signal'] is not None]
            signal_distribution = {
                'buy': signals_list.count('buy'),
                'sell': signals_list.count('sell'),
                'hold': len(chart_data) - len(signals_list)
            }
            
            # --- Generate Resumen TXT ---
            report_data = {
                "metrics": {
                    "initial_balance": initial_balance,
                    "final_balance": final_balance,
                    "profit_pct": profit_pct,
                    "profit_factor": profit_factor,
                    "max_drawdown": max_drawdown,
                    "sharpe_ratio": sharpe_ratio,
                    "win_rate": win_rate
                },
                "counts": {
                    "total": len(close_trades),
                    "buy": len([t for t in trades if t['type'] == 'BUY']),
                    "sell": len([t for t in trades if t['type'] == 'SELL_SHORT'])
                },
                "trades": trades,
                "candles": chart_data
            }
            
            report_path = self._generate_backtest_report(symbol, selected_strategy_name, report_data)

            # 7. Bot Configuration
            bot_config = {
                "strategy_type": selected_strategy_name,
                "symbol": symbol,
                "timeframe": timeframe,
                "model_id": model_used,
                "parameters": {
                    "ml_confidence": ml_confidence,
                    "take_profit_pct": take_profit_pct,
                    "stop_loss_pct": stop_loss_pct,
                    "leverage": 1,
                    "initial_balance": initial_balance
                }
            }
            
            logger.info(f"🏁 Backtest completed. Trades: {len(close_trades)}, Profit: {profit_pct:.2f}%")
            
            return {
                "status": "success",
                "strategy_name": selected_strategy_name,
                "model_used": model_used,
                "ml_confidence": ml_confidence,
                "optimized_parameters": {
                    "take_profit_pct": take_profit_pct,
                    "stop_loss_pct": stop_loss_pct,
                    "expected_win_rate": 0
                },
                "metrics": {
                    "initial_balance": initial_balance,
                    "final_balance": final_balance,
                    "profit_pct": profit_pct,
                    "profit_factor": profit_factor,
                    "total_trades": len(close_trades),
                    "long_trades": len(long_trades),
                    "short_trades": len(short_trades),
                    "buy_count": len([t for t in trades if t['type'] == 'BUY']),
                    "sell_count": len([t for t in trades if t['type'] == 'SELL_SHORT']),
                    "win_rate": win_rate,
                    "max_drawdown": abs(max_drawdown),
                    "sharpe_ratio": round(sharpe_ratio, 2),
                    "signal_distribution": signal_distribution,
                    "report_path": report_path
                },
                "trades": trades,
                "chart_data": chart_data,
                "bot_configuration": bot_config
            }
            
        except Exception as e:
            logger.error(f"Error in backtest run: {e}")
            import traceback
            traceback.print_exc()
            return {"error": str(e)}

    async def _get_user_virtual_balance(self, user_id: str, market_type: str = "CEX", asset: str = "USDT") -> float:
        try:
            # 1. Resolver User ID
            user = await db.users.find_one({"openId": user_id})
            if not user:
                logger.warning(f"User {user_id} not found, defaulting to 10000")
                return 10000.0
                
            # 2. Obtener Balance
            balance_doc = await db.virtual_balances.find_one({
                "userId": user["_id"], 
                "marketType": market_type, 
                "asset": asset
            })
            
            if balance_doc:
                return float(balance_doc.get("amount", 10000.0))
            
            # Default si no existe
            return 10000.0
            
        except Exception as e:
            logger.error(f"Error fetching virtual balance: {e}")
            return 10000.0

    def _generate_backtest_report(self, symbol: str, strategy: str, data: dict) -> str:
        """Generates a detailed TXT report of the backtest."""
        import os
        from datetime import datetime
        
        reports_dir = "api/data/reports"
        os.makedirs(reports_dir, exist_ok=True)
        
        safe_symbol = symbol.replace('/', '_')
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{reports_dir}/Report_{strategy}_{safe_symbol}_{timestamp}.txt"
        
        metrics = data.get('metrics', {})
        counts = data.get('counts', {})
        
        content = [
            "==================================================",
            f"          REPORTE DE BACKTEST - {symbol}",
            "==================================================",
            f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"Estrategia: {strategy}",
            "==================================================",
            "METRICAS FINANCIERAS:",
            f"Balance Inicial:   ${metrics.get('initial_balance', 0):,.2f}",
            f"Balance Final:     ${metrics.get('final_balance', 0):,.2f}",
            f"Retorno Total:     {metrics.get('profit_pct', 0):.2f}%",
            f"Profit Factor:     {metrics.get('profit_factor', 0)}",
            f"Max Drawdown:      {metrics.get('max_drawdown', 0):.2f}%",
            f"Sharpe Ratio:      {metrics.get('sharpe_ratio', 0):.2f}",
            "",
            "ESTADISTICAS OPERATIVAS:",
            f"Total Operaciones: {counts.get('total', 0)}",
            f"Compras (BUY):     {counts.get('buy', 0)}",
            f"Ventas (SELL):     {counts.get('sell', 0)}",
            f"Win Rate:          {metrics.get('win_rate', 0):.1f}%",
            "==================================================",
            "DETALLE DE VELAS Y SEÑALES (Últimas 500):",
            "Fecha                 | Apertura | Cierre   | Señal    | Equity",
            "------------------------------------------------------------------"
        ]
        
        # Add Candle Data (Limit to avoid massive files if needed, or full)
        candles = data.get('candles', [])
        for c in candles: # List all
            date_str = pd.to_datetime(c['time'], unit='ms').strftime('%Y-%m-%d %H:%M')
            signal = c.get('signal', '-') or '-'
            line = f"{date_str:<21} | {c['open']:<8.2f} | {c['close']:<8.2f} | {signal:<8} | {c['equity']:.2f}"
            content.append(line)
            
        content.append("==================================================")
        content.append("REGISTRO DE OPERACIONES (TRADES):")
        for t in data.get('trades', []):
            content.append(str(t))
            
        with open(filename, 'w', encoding='utf-8') as f:
            f.write('\\n'.join(content))
            
        logger.info(f"Report generated at: {filename}")
        return filename
