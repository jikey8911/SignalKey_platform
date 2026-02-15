```json
{
    "analysis": "The current strategy has a high win rate but still experiences significant drawdowns. The worst losses occurred when the strategy entered long positions during a downtrend, indicating the need for additional trend confirmation. The best wins happened when the strategy caught strong uptrends, emphasizing the importance of trend alignment. To improve the strategy, we need to incorporate additional filters to avoid buying in downtrends and consider volatility to reduce the risk of large losses.",
    "modifications": [
        "Added a trend confirmation using a longer-term EMA (50 periods) to filter out downtrends.",
        "Incorporated an RSI check to avoid overbought conditions when entering long positions and oversold conditions when entering short positions.",
        "Implemented a volatility filter using the ATR (Average True Range) to avoid trading during highly volatile periods."
    ],
    "expected_profit_pct": 38.0,
    "expected_win_rate": 95.0,
    "code": "
import pandas as pd
from api.src.domain.strategies.base import BaseStrategy

class OptimizedTrendEma(BaseStrategy):
    def __init__(self, config=None):
        super().__init__(config or {})
        self.fast = 9
        self.slow = 21
        self.trend = 50
        self.rsi_period = 14

    def apply(self, df: pd.DataFrame, current_position: dict = None) -> pd.DataFrame:
        df['ema_f'] = df['close'].ewm(span=self.fast).mean()
        df['ema_s'] = df['close'].ewm(span=self.slow).mean()
        df['ema_t'] = df['close'].ewm(span=self.trend).mean()
        df['vol_sma'] = df['volume'].rolling(window=20).mean()
        
        # Calculate RSI
        delta = df['close'].diff(1)
        gain, loss = delta.copy(), delta.copy()
        gain[gain < 0] = 0
        loss[loss > 0] = 0
        avg_gain = gain.ewm(com=self.rsi_period-1, adjust=False).mean()
        avg_loss = loss.ewm(com=self.rsi_period-1, adjust=False).mean().abs()
        RS = avg_gain / avg_loss
        df['rsi'] = 100.0 - (100.0 / (1.0 + RS))
        
        # Calculate ATR
        high_low = df['high'] - df['low']
        high_close = (df['high'] - df['close'].shift(1)).abs()
        low_close = (df['low'] - df['close'].shift(1)).abs()
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        df['atr'] = ranges.max(axis=1).rolling(window=14).mean()
        
        # Features
        df['ema_diff'] = (df['ema_f'] - df['ema_s']) / df['ema_s']
        df['vol_ratio'] = df['volume'] / df['vol_sma']

        df['signal'] = self.SIGNAL_WAIT
        
        # LONG: Cruce alcista + Volumen superior al promedio + EMA tendencia alcista + RSI no sobrecomprado + ATR bajo
        df.loc[(df['ema_f'] > df['ema_s']) & (df['ema_s'] > df['ema_t']) & (df['vol_ratio'] > 1.2) & (df['rsi'] < 70) & (df['atr'] < df['atr'].mean()), 'signal'] = self.SIGNAL_BUY
        
        # SHORT: Cruce bajista + Volumen superior al promedio + EMA tendencia bajista + RSI no sobrevenido + ATR bajo
        df.loc[(df['ema_f'] < df['ema_s']) & (df['ema_s'] < df['ema_t']) & (df['vol_ratio'] > 1.2) & (df['rsi'] > 30) & (df['atr'] < df['atr'].mean()), 'signal'] = self.SIGNAL_SELL
        
        return df

    def get_features(self):
        return ['ema_diff', 'vol_ratio', 'rsi', 'atr']
"
}
```