import ccxt
import pandas as pd
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from api.infrastructure.adapters.ai_adapter import AIAdapter
from api.services.ml_service import MLService
from api.models.mongodb import db

logger = logging.getLogger(__name__)

class BacktestService:
    def __init__(self, ai_adapter: Optional[AIAdapter] = None):
        self.exchange = ccxt.binance()  # Por defecto para datos históricos
        self.ai_adapter = ai_adapter or AIAdapter()
        self.ml_service = MLService()

    async def run_backtest(
        self, 
        symbol: str, 
        days: int = 7, 
        timeframe: str = '1h',
        use_ai: bool = False,
        user_config: Dict[str, Any] = None,
        strategy: str = "standard",
        user_id: str = "default_user",
        initial_balance: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Ejecuta backtest. Si strategy='auto', ejecuta torneo de estrategias.
        Usa balance virtual del usuario si está disponible.
        """
        logger.info(f"Iniciando backtest para {symbol} en los últimos {days} días (AI: {use_ai}, Strategy: {strategy})")
        
        # Obtener balance virtual del usuario
        if initial_balance is None:
            initial_balance = await self._get_user_virtual_balance(user_id)
        
        logger.info(f"Using initial balance: ${initial_balance} for user {user_id}")
        
        try:
            # 1. Obtener datos históricos
            since = self.exchange.parse8601((datetime.now() - timedelta(days=days)).isoformat())
            ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe, since)
            
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            
            # 2. Modo Torneo (Auto)
            if use_ai and strategy == "auto":
                return await self._run_strategy_tournament(df, symbol, user_config, initial_balance)
            
            # 3. Modo ML Local
            if use_ai and strategy == "local_lstm":
                return await self._run_ml_backtest(df, symbol, timeframe, initial_balance)

            # 4. Modo Selección Manual (AI Externo)
            if use_ai and user_config:
                return await self._run_ai_backtest(df, symbol, user_config, strategy, initial_balance)
            else:
                return await self._run_sma_backtest(df, symbol, initial_balance)
                
        except Exception as e:
            logger.error(f"Error en backtest: {e}")
            return {"error": str(e)}
    
    async def _get_user_virtual_balance(self, user_id: str, market_type: str = "CEX", asset: str = "USDT") -> float:
        """
        Obtiene el balance virtual del usuario desde MongoDB.
        Retorna balance por defecto si no existe.
        """
        try:
            user = await db.users.find_one({"openId": user_id})
            if not user:
                logger.warning(f"User {user_id} not found, using default balance")
                return 10000.0
            
            balance_doc = await db.virtual_balances.find_one({
                "userId": user["_id"],
                "marketType": market_type,
                "asset": asset
            })
            
            if balance_doc and "amount" in balance_doc:
                balance = float(balance_doc["amount"])
                logger.info(f"Using virtual balance for {user_id}: ${balance}")
                return balance
            else:
                logger.warning(f"No virtual balance found for {user_id}, using default")
                return 10000.0
                
        except Exception as e:
            logger.error(f"Error retrieving virtual balance: {e}")
            return 10000.0

    async def _run_ml_backtest(self, df: pd.DataFrame, symbol: str, timeframe: str, initial_balance: float = 10000.0) -> Dict[str, Any]:
        """
        Backtest usando modelo local LSTM.
        """
        logger.info(f"Running Local Neutral Network backtest for {symbol} with balance ${initial_balance}")
        candles = df.to_dict('records')
        trades = []
        balance = initial_balance
        position = 0
        entry_price = 0
        
        # Iterar velas (simulando paso a paso)
        # Empezamos en index 60 porque el modelo necesita 60 velas de contexto
        seq_length = 60
        
        for i in range(seq_length, len(candles)):
            current_candle = candles[i]
            current_price = current_candle['close']
            
            # Contexto
            context = candles[i-seq_length:i]
            
            # Predicción (Nota: Esto será lento si no se optimiza con batching real)
            # Para MVP está bien.
            prediction = self.ml_service.predict(symbol, timeframe, context)
            
            decision = prediction.get("decision", "HOLD")
            confidence = prediction.get("confidence", 0)
            
            # Lógica de Trading
            if decision == "BUY" and balance > 0:
                position = balance / current_price
                entry_price = current_price
                balance = 0
                trades.append({
                    'type': 'BUY',
                    'price': current_price,
                    'time': current_candle['timestamp'],
                    'confidence': confidence,
                    'reasoning': prediction.get("reasoning", "")
                })
            
            elif decision == "SELL" and position > 0:
                balance = position * current_price
                pnl = ((current_price - entry_price) / entry_price) * 100
                position = 0
                trades.append({
                    'type': 'SELL',
                    'price': current_price,
                    'time': current_candle['timestamp'],
                    'pnl': pnl,
                    'confidence': confidence,
                    'reasoning': prediction.get("reasoning", "")
                })
        
        # Cerrar posición final
        if position > 0:
            final_price = candles[-1]['close']
            balance = position * final_price
            trades.append({'type': 'SELL', 'price': final_price, 'time': candles[-1]['timestamp'], 'pnl': 0, 'reason': 'End'})

        profit_pct = ((balance - initial_balance) / initial_balance) * 100
        
        return {
            "symbol": symbol,
            "strategy_used": "local_lstm",
            "initial_balance": initial_balance,
            "final_balance": balance,
            "profit_percentage": profit_pct,
            "total_trades": len(trades),
            "trades": trades[-20:] # Return last 20
        }


    async def _run_strategy_tournament(self, df: pd.DataFrame, symbol: str, user_config: Dict[str, Any], initial_balance: float = 10000.0) -> Dict[str, Any]:
        """
        Ejecuta todas las estrategias y retorna la mejor.
        """
        logger.info(f"🏆 Iniciando Torneo de Estrategias para {symbol} con balance ${initial_balance}...")
        
        # 1. Definir competidores
        strategies = ["sma", "standard", "sniper"]
        results = []
        
        # 2. Ejecutar SMA (Baseline)
        try:
            sma_res = await self._run_sma_backtest(df, symbol, initial_balance)
            sma_res["strategy_name"] = "SMA (Cruce Medias)"
            sma_res["strategy_id"] = "sma"
            results.append(sma_res)
        except Exception as e:
            logger.error(f"Error en SMA strategy: {e}")

        # 3. Ejecutar Estrategias de AI
        # Nota: Esto puede ser lento. En producción se haría en paralelo con asyncio.gather
        for strat in ["standard", "sniper"]:
            try:
                ai_res = await self._run_ai_backtest(df, symbol, user_config, strat, initial_balance)
                ai_res["strategy_name"] = f"AI {strat.capitalize()}"
                ai_res["strategy_id"] = strat
                results.append(ai_res)
            except Exception as e:
                logger.error(f"Error en AI strategy {strat}: {e}")
        
        # 4. Seleccionar Ganador
        if not results:
            raise Exception("Ninguna estrategia pudo completarse exitosamente")
            
        # Criterio: Score = Profit% * 0.7 + WinRate% * 0.3
        # Penaliza drawdown si lo tuviéramos
        best_score = -float('inf')
        winner = results[0]
        
        for res in results:
            profit = float(res.get("profit_percentage", 0))
            win_rate = float(res.get("win_rate", 0))
            total_trades = int(res.get("total_trades", 0))
            
            # Penalizar si no opera
            if total_trades == 0:
                score = -100
            else:
                score = (profit * 0.7) + (win_rate * 0.3)
            
            logger.info(f"Strategy {res['strategy_name']} Score: {score} (Profit: {profit}%, WR: {win_rate}%)")
            
            if score > best_score:
                best_score = score
                winner = res
        
        winner["recommended"] = True
        winner["tournament_results"] = [
            {
                "id": r["strategy_id"], 
                "name": r["strategy_name"], 
                "profit": r["profit_percentage"], 
                "trades": r["total_trades"]
            } 
            for r in results
        ]
        
        logger.info(f"🏆 Ganador del torneo: {winner['strategy_name']} (Profit: {winner['profit_percentage']}%)")
        return winner

    async def _run_ai_backtest(self, df: pd.DataFrame, symbol: str, user_config: Dict[str, Any], strategy: str = "standard", initial_balance: float = 10000.0) -> Dict[str, Any]:
        """
        Ejecuta backtest usando IA para generar señales.
        """
        logger.info(f"Running AI-powered backtest for {symbol} with strategy {strategy} and balance ${initial_balance}")
        
        # Convertir DataFrame a lista de diccionarios para el AI adapter
        candles = df.to_dict('records')
        
        # Configuración de ventana y paso
        window_size = 20  # Contexto de 20 velas
        step_size = 5     # Analizar cada 5 velas (optimización de costos)
        
        # Obtener señales de la IA
        signals = await self.ai_adapter.analyze_historical_batch(
            candles=candles,
            window_size=window_size,
            step_size=step_size,
            config=user_config,
            strategy_name=strategy
        )
        
        # Inicializar balance y métricas
        balance = initial_balance
        position = 0
        position_entry_price = 0
        trades = []
        
        # Métricas de IA
        ai_confidences = []
        
        # Procesar cada señal
        for signal_index, signal_analysis in signals:
            current_price = df.iloc[signal_index]['close']
            ai_confidences.append(signal_analysis.confidence)
            
            # Señal de compra
            if signal_analysis.decision.value == "BUY" and balance > 0:
                # Invertir todo el balance disponible
                position = balance / current_price
                position_entry_price = current_price
                balance = 0
                
                trades.append({
                    'type': 'BUY',
                    'price': current_price,
                    'time': df.iloc[signal_index]['timestamp'],
                    'confidence': signal_analysis.confidence,
                    'reasoning': signal_analysis.reasoning[:100]  # Truncar para reporte
                })
                
                logger.info(f"AI BUY signal at {current_price} (confidence: {signal_analysis.confidence:.2f})")
            
            # Señal de venta
            elif signal_analysis.decision.value == "SELL" and position > 0:
                # Vender toda la posición
                balance = position * current_price
                pnl = ((current_price - position_entry_price) / position_entry_price) * 100
                position = 0
                
                trades.append({
                    'type': 'SELL',
                    'price': current_price,
                    'time': df.iloc[signal_index]['timestamp'],
                    'pnl': pnl,
                    'confidence': signal_analysis.confidence,
                    'reasoning': signal_analysis.reasoning[:100]
                })
                
                logger.info(f"AI SELL signal at {current_price} (PnL: {pnl:.2f}%)")
        
        # Cerrar posición final si está abierta
        if position > 0:
            final_price = df.iloc[-1]['close']
            balance = position * final_price
            pnl = ((final_price - position_entry_price) / position_entry_price) * 100
            trades.append({
                'type': 'SELL',
                'price': final_price,
                'time': df.iloc[-1]['timestamp'],
                'pnl': pnl,
                'reason': 'End of backtest period'
            })
        
        # Calcular métricas finales
        final_value = balance
        profit_pct = ((final_value - initial_balance) / initial_balance) * 100
        
        winning_trades = [t for t in trades if t.get('pnl', 0) > 0]
        losing_trades = [t for t in trades if t.get('pnl', 0) < 0]
        
        # Calcular max drawdown
        equity_curve = [initial_balance]
        current_equity = initial_balance
        for trade in trades:
            if trade['type'] == 'SELL' and 'pnl' in trade:
                current_equity = current_equity * (1 + trade['pnl'] / 100)
                equity_curve.append(current_equity)
        
        max_drawdown = 0
        peak = equity_curve[0]
        for value in equity_curve:
            if value > peak:
                peak = value
            drawdown = ((peak - value) / peak) * 100
            if drawdown > max_drawdown:
                max_drawdown = drawdown
        
        return {
            "symbol": symbol,
            "strategy_used": "ai",
            "initial_balance": initial_balance,
            "final_balance": final_value,
            "profit_percentage": profit_pct,
            "total_trades": len([t for t in trades if t['type'] == 'BUY']),
            "winning_trades": len(winning_trades),
            "losing_trades": len(losing_trades),
            "win_rate": (len(winning_trades) / len([t for t in trades if t['type'] == 'BUY'])) * 100 if len([t for t in trades if t['type'] == 'BUY']) > 0 else 0,
            "max_drawdown": max_drawdown,
            "ai_confidence_avg": sum(ai_confidences) / len(ai_confidences) if ai_confidences else 0,
            "ai_decisions_count": len(signals),
            "equity_curve": equity_curve,
            "trades": trades[-20:]  # Últimos 20 trades para el reporte
        }

    async def _run_sma_backtest(self, df: pd.DataFrame, symbol: str, initial_balance: float = 10000.0) -> Dict[str, Any]:
        """
        Ejecuta backtest usando estrategia simple de cruce de medias móviles (legacy).
        """
        logger.info(f"Running SMA backtest for {symbol} with balance ${initial_balance}")
        
        balance = initial_balance
        trades = []
        
        # Estrategia simple de cruce de medias
        df['sma_short'] = df['close'].rolling(window=10).mean()
        df['sma_long'] = df['close'].rolling(window=30).mean()
        
        position = 0
        for i in range(1, len(df)):
            # Señal de compra
            if df['sma_short'].iloc[i] > df['sma_long'].iloc[i] and df['sma_short'].iloc[i-1] <= df['sma_long'].iloc[i-1]:
                if balance > 0:
                    position = balance / df['close'].iloc[i]
                    balance = 0
                    trades.append({'type': 'BUY', 'price': df['close'].iloc[i], 'time': df['timestamp'].iloc[i]})
            
            # Señal de venta
            elif df['sma_short'].iloc[i] < df['sma_long'].iloc[i] and df['sma_short'].iloc[i-1] >= df['sma_long'].iloc[i-1]:
                if position > 0:
                    balance = position * df['close'].iloc[i]
                    position = 0
                    trades.append({'type': 'SELL', 'price': df['close'].iloc[i], 'time': df['timestamp'].iloc[i]})

        final_value = balance + (position * df['close'].iloc[-1] if position > 0 else 0)
        profit_pct = ((final_value - initial_balance) / initial_balance) * 100
        
        # Calcular max drawdown
        equity_curve = [initial_balance]
        current_equity = initial_balance
        for trade in trades:
            if trade['type'] == 'SELL':
                # Estimar P&L basado en el precio
                current_equity = final_value  # Simplificación para SMA
                equity_curve.append(current_equity)
        
        max_drawdown = 0
        peak = equity_curve[0]
        for value in equity_curve:
            if value > peak:
                peak = value
            drawdown = ((peak - value) / peak) * 100
            if drawdown > max_drawdown:
                max_drawdown = drawdown
        
        return {
            "symbol": symbol,
            "strategy_used": "sma",
            "initial_balance": initial_balance,
            "final_balance": final_value,
            "profit_percentage": profit_pct,
            "total_trades": len(trades),
            "max_drawdown": max_drawdown,
            "trades": trades[-10:]  # Últimos 10 trades
        }

