import ccxt
import pandas as pd
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class BacktestService:
    def __init__(self):
        self.exchange = ccxt.binance() # Por defecto para datos históricos

    async def run_backtest(self, symbol: str, days: int = 7, timeframe: str = '1h'):
        logger.info(f"Iniciando backtest para {symbol} en los últimos {days} días")
        
        try:
            # 1. Obtener datos históricos
            since = self.exchange.parse8601((datetime.now() - timedelta(days=days)).isoformat())
            ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe, since)
            
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            
            # 2. Simulación básica (aquí se integraría la lógica de señales)
            # En un caso real, pasaríamos cada vela a Gemini o aplicaríamos una estrategia
            
            initial_balance = 10000.0
            balance = initial_balance
            trades = []
            
            # Ejemplo: Estrategia simple de cruce de medias para ilustrar el backtest
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
            
            return {
                "symbol": symbol,
                "initial_balance": initial_balance,
                "final_balance": final_value,
                "profit_percentage": profit_pct,
                "total_trades": len(trades),
                "trades": trades[-10:] # Últimos 10 trades
            }

        except Exception as e:
            logger.error(f"Error en backtest: {e}")
            return {"error": str(e)}
