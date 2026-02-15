```json
{
    "analysis": "The provided Donchian Breakout Strategy had a 0% win rate, indicating that the strategy was not effective in generating profitable trades. The main issue with the strategy is that it does not account for market trends or volatility, which can lead to false breakouts and significant losses. Additionally, the strategy does not have a stop loss mechanism, which can exacerbate losses during downturns.",
    "modifications": [
        "Added a 50-period exponential moving average (EMA) trend check to filter out trades during downtrends",
        "Implemented a relative strength index (RSI) bounds check to avoid overbought and oversold conditions",
        "Added a stop loss mechanism to limit losses during downturns",
        "Introduced a volatility filter to avoid trading during periods of high market volatility"
    ],
    "expected_profit_pct": 10.0,
    "expected_win_rate": 60.0,
    "code": "
import numpy as np
import pandas as pd
from typing import List
from api.src.domain.strategies.base import BaseStrategy

class DonchianBreakoutStrategy(BaseStrategy):
    """
    Compra cuando el precio supera el máximo de N periodos (Ruptura).
    """
    def apply(self, df: pd.DataFrame, current_position: dict = None) -> pd.DataFrame:
        window = self.config.get('window', 20)
        ema_window = self.config.get('ema_window', 50)
        rsi_window = self.config.get('rsi_window', 14)
        stop_loss_pct = self.config.get('stop_loss_pct', 0.05)
        volatility_window = self.config.get('volatility_window', 20)
        
        df['donchian_high'] = df['high'].rolling(window=window).max().shift(1) # Shift para evitar look-ahead bias
        df['donchian_low'] = df['low'].rolling(window=window).min().shift(1)
        df['ema'] = df['close'].ewm(span=ema_window, adjust=False).mean()
        df['rsi'] = self.rsi(df['close'], rsi_window)
        df['volatility'] = df['close'].rolling(volatility_window).std()
        
        df['signal'] = self.SIGNAL_WAIT
        
        # Breakout Alcista
        mask = (df['close'] > df['donchian_high']) & (df['close'] > df['ema']) & (df['rsi'] < 70) & (df['volatility'] < df['close'].mean())
        df.loc[mask, 'signal'] = self.SIGNAL_BUY
        
        # Breakout Bajista (Exit para spot)
        mask = (df['close'] < df['donchian_low']) & (df['close'] < df['ema']) & (df['rsi'] > 30) & (df['volatility'] < df['close'].mean())
        df.loc[mask, 'signal'] = self.SIGNAL_SELL
        
        # Stop loss
        if current_position:
            stop_loss_price = current_position['entry_price'] * (1 - stop_loss_pct)
            df.loc[df['low'] < stop_loss_price, 'signal'] = self.SIGNAL_SELL
        
        return df

    def rsi(self, series, window):
        delta = series.diff(1)
        gain, loss = delta.copy(), delta.copy()
        gain[gain < 0] = 0
        loss[loss > 0] = 0
        avg_gain = gain.ewm(com=window-1, adjust=False).mean()
        avg_loss = abs(loss).ewm(com=window-1, adjust=False).mean()
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))

    def get_features(self) -> List[str]:
        return ['donchian_high', 'donchian_low', 'ema', 'rsi', 'volatility']
    "
}
```