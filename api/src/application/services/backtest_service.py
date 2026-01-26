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
            
            # 4. Optimizar Parámetros TP/SL
            logger.info(f"🔧 Optimizing trade parameters...")
            optimal_params = self.optimize_trade_parameters(
                selected_strategy,
                candles,
                df,
                initial_balance,
                user_config
            )
            
            take_profit_pct = optimal_params['take_profit_pct']
            stop_loss_pct = optimal_params['stop_loss_pct']
            logger.info(f"✅ Optimal TP: {take_profit_pct}%, SL: {stop_loss_pct}%")
            
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
                
                # Crear contexto de posición para la estrategia
                position_context = {
                    'has_position': total_long > 0 or total_short > 0,
                    'position_type': 'LONG' if total_long > 0 else ('SHORT' if total_short > 0 else None),
                    'avg_entry_price': avg_long_price if total_long > 0 else (avg_short_price if total_short > 0 else 0),
                    'current_price': current_price,
                    'unrealized_pnl_pct': unrealized_pnl_pct,
                    'position_count': len(long_positions) if total_long > 0 else len(short_positions)
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
                    "expected_win_rate": optimal_params.get('win_rate', 0)
                },
                "metrics": {
                    "initial_balance": initial_balance,
                    "final_balance": final_balance,
                    "profit_pct": profit_pct,
                    "total_trades": len(close_trades),
                    "long_trades": len(long_trades),
                    "short_trades": len(short_trades),
                    "win_rate": win_rate,
                    "max_drawdown": abs(max_drawdown)
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
            # Simple wrapper to avoid circular dependency issues or reuse logic
            # For now simplified:
            return 10000.0
        except:
            return 10000.0


# Nuevo código para BacktestService - Métodos a agregar

def optimize_trade_parameters(self, strategy, candles, df, initial_balance, user_config):
    """
    Optimiza take-profit y stop-loss mediante grid search.
    
    Returns:
        {
            "take_profit_pct": 2.0,
            "stop_loss_pct": 1.5,
            "expected_profit": 15.3,
            "win_rate": 68.5
        }
    """
    logger.info("🔧 Optimizing trade parameters...")
    
    # Opciones a probar
    tp_options = [0.5, 1.0, 1.5, 2.0, 3.0, 5.0]
    sl_options = [0.5, 1.0, 1.5, 2.0, 3.0]
    
    best_params = None
    best_score = -float('inf')
    
    for tp in tp_options:
        for sl in sl_options:
            # Ejecutar mini-backtest
            result = self._run_mini_backtest(
                strategy=strategy,
                candles=candles,
                df=df,
                initial_balance=initial_balance,
                take_profit_pct=tp,
                stop_loss_pct=sl,
                user_config=user_config
            )
            
            # Métrica: Profit ajustado por riesgo
            profit = result['final_balance'] - initial_balance
            max_dd = abs(result.get('max_drawdown', 0))
            
            # Penalizar si hay muy pocas operaciones
            num_trades = result.get('total_trades', 0)
            if num_trades < 2:
                continue
            
            # Score: profit / (1 + drawdown)
            risk_adjusted_profit = profit / (1 + max_dd) if max_dd > 0 else profit
            
            if risk_adjusted_profit > best_score:
                best_score = risk_adjusted_profit
                best_params = {
                    "take_profit_pct": tp,
                    "stop_loss_pct": sl,
                    "expected_profit": round(profit, 2),
                    "win_rate": round(result.get('win_rate', 0), 2),
                    "total_trades": num_trades
                }
    
    if not best_params:
        # Fallback a valores conservadores
        best_params = {
            "take_profit_pct": 2.0,
            "stop_loss_pct": 1.5,
            "expected_profit": 0,
            "win_rate": 0,
            "total_trades": 0
        }
    
    logger.info(f"✅ Optimal TP: {best_params['take_profit_pct']}%, SL: {best_params['stop_loss_pct']}%")
    return best_params


def _run_mini_backtest(self, strategy, candles, df, initial_balance, take_profit_pct, stop_loss_pct, user_config):
    """
    Ejecuta un backtest rápido con parámetros específicos de TP/SL.
    """
    virtual_balance = initial_balance
    positions = []
    total_position = 0
    avg_entry_price = 0
    fee = 0.001
    
    trades = []
    equity_curve = []
    
    investment_limits = user_config.get("investmentLimits", {}) if user_config else {}
    max_amount_cfg = investment_limits.get("cexMaxAmount", 100.0)
    
    for i in range(len(candles)):
        candle = candles[i]
        current_price = candle['close']
        
        # Obtener señal de la estrategia
        window_slice = df.iloc[max(0, i - 100) : i + 1]
        try:
            signal_result = strategy.get_signal(window_slice)
            algo_signal = signal_result.get('signal', 'hold')
        except:
            algo_signal = 'hold'
        
        # Verificar TP/SL si hay posición
        if total_position > 0:
            take_profit_price = avg_entry_price * (1 + take_profit_pct / 100)
            stop_loss_price = avg_entry_price * (1 - stop_loss_pct / 100)
            
            if current_price >= take_profit_price:
                algo_signal = 'sell'
            elif current_price <= stop_loss_price:
                algo_signal = 'sell'
        
        # COMPRA (acumulativa)
        if algo_signal == 'buy' and virtual_balance > 0:
            amount_to_spend = min(float(max_amount_cfg), virtual_balance * 0.98)
            coin_amount = amount_to_spend / current_price
            cost = coin_amount * current_price
            fee_cost = cost * fee
            
            virtual_balance -= (cost + fee_cost)
            
            positions.append({
                'price': current_price,
                'amount': coin_amount,
                'cost': cost
            })
            
            total_position += coin_amount
            total_cost = sum(p['cost'] for p in positions)
            avg_entry_price = total_cost / total_position
            
            trades.append({'type': 'BUY', 'price': current_price})
        
        # VENTA (total)
        elif algo_signal == 'sell' and total_position > 0:
            revenue = total_position * current_price
            fee_cost = revenue * fee
            total_return = revenue - fee_cost
            
            pnl_pct = ((current_price - avg_entry_price) / avg_entry_price) * 100
            virtual_balance += total_return
            
            trades.append({'type': 'SELL', 'price': current_price, 'pnl_pct': pnl_pct})
            
            positions = []
            total_position = 0
            avg_entry_price = 0
        
        # Track equity
        current_equity = virtual_balance + (total_position * current_price if total_position > 0 else 0)
        equity_curve.append(current_equity)
    
    # Cerrar posición final si existe
    if total_position > 0:
        final_price = candles[-1]['close']
        revenue = total_position * final_price
        virtual_balance += (revenue - revenue * fee)
    
    # Calcular métricas
    final_balance = virtual_balance
    sell_trades = [t for t in trades if t['type'] == 'SELL']
    winning_trades = [t for t in sell_trades if t.get('pnl_pct', 0) > 0]
    win_rate = (len(winning_trades) / len(sell_trades) * 100) if sell_trades else 0
    
    # Max drawdown
    if equity_curve:
        peak = equity_curve[0]
        max_dd = 0
        for equity in equity_curve:
            if equity > peak:
                peak = equity
            dd = ((equity - peak) / peak) * 100
            if dd < max_dd:
                max_dd = dd
    else:
        max_dd = 0
    
    return {
        'final_balance': final_balance,
        'win_rate': win_rate,
        'total_trades': len(sell_trades),
        'max_drawdown': max_dd
    }
