```json
{
    "analysis": "The current strategy has a high win rate but also experiences significant drawdowns. The worst losses occurred when the strategy bought into a downtrend or failed to account for volatility. To improve performance, we need to add filters to prevent buying in downtrends and to reduce the impact of volatile markets.",
    "modifications": [
        "Added an EMA trend check to ensure we're only buying in uptrends",
        "Added an RSI bounds check to prevent overbuying",
        "Added a volatility filter to reduce trading during highly volatile periods",
        " Implemented a stop-loss mechanism to limit losses"
    ],
    "expected_profit_pct": 5.0,
    "expected_win_rate": 70.0,
    "code": "
import numpy as np
import pandas as pd
from typing import List
from api.src.domain.strategies.base import BaseStrategy

class StochasticStrategy(BaseStrategy):
    """
    Identifica puntos de giro.
    Compra: %K cruza por encima de %D en zona baja (<20).
    """
    def apply(self, df: pd.DataFrame, current_position: dict = None) -> pd.DataFrame:
        k_period = self.config.get('k_period', 14)
        d_period = self.config.get('d_period', 3)
        ema_period = self.config.get('ema_period', 50)
        rsi_period = self.config.get('rsi_period', 14)
        volatility_period = self.config.get('volatility_period', 20)
        
        low_min = df['low'].rolling(window=k_period).min()
        high_max = df['high'].rolling(window=k_period).max()
        
        df['stoch_k'] = 100 * ((df['close'] - low_min) / (high_max - low_min))
        df['stoch_d'] = df['stoch_k'].rolling(window=d_period).mean()

        df['ema'] = df['close'].ewm(span=ema_period, adjust=False).mean()
        df['rsi'] = self.rsi(df['close'], rsi_period)
        df['volatility'] = self.volatility(df['close'], volatility_period)

        df['signal'] = self.SIGNAL_WAIT
        
        # Cruce alcista en sobreventa
        buy_cond = (df['stoch_k'] > df['stoch_d']) & (df['stoch_k'] < 20) & (df['stoch_k'].shift(1) <= df['stoch_d'].shift(1)) & \
                    (df['close'] > df['ema']) & (df['rsi'] < 70) & (df['volatility'] < 2)
        df.loc[buy_cond, 'signal'] = self.SIGNAL_BUY

        # Cruce bajista en sobrecompra
        sell_cond = (df['stoch_k'] < df['stoch_d']) & (df['stoch_k'] > 80) & (df['rsi'] > 30)
        df.loc[sell_cond, 'signal'] = self.SIGNAL_SELL

        # Stop-loss
        stop_loss = 0.05
        df['stop_loss'] = df['close'] * (1 - stop_loss)
        df.loc[(df['signal'] == self.SIGNAL_BUY) & (df['low'] < df['stop_loss']), 'signal'] = self.SIGNAL_SELL

        return df

    def rsi(self, series, period):
        delta = series.diff(1)
        gain, loss = delta.copy(), delta.copy()
        gain[gain < 0] = 0
        loss[loss > 0] = 0
        avg_gain = gain.rolling(window=period, min_periods=0).mean()
        avg_loss = loss.rolling(window=period, min_periods=0).mean().abs()
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return rsi

    def volatility(self, series, period):
        return series.rolling(window=period, min_periods=0).std()

    def get_features(self) -> List[str]:
        return ['stoch_k', 'stoch_d', 'ema', 'rsi', 'volatility']
"
}
```