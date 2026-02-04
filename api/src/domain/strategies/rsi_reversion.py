import pandas as pd
from .base import BaseStrategy

class RsiReversion(BaseStrategy):
    """
    Estrategia de reversión pura basada en RSI extremo y 
    agotamiento de precio.
    """
    def __init__(self, config=None):
        super().__init__(config or {})
        self.rsi_period = int(self.config.get('rsi_period', 14))
        self.oversold = int(self.config.get('oversold', 25))
        self.overbought = int(self.config.get('overbought', 75))

    def apply(self, df: pd.DataFrame, current_position: dict = None) -> pd.DataFrame:
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=self.rsi_period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=self.rsi_period).mean()
        df['rsi'] = 100 - (100 / (1 + (gain / loss)))
        
        # Rate of Change (ROC) como feature adicional
        df['roc'] = df['close'].pct_change(periods=5)

        df['signal'] = self.SIGNAL_WAIT
        
        # LONG: RSI extremadamente bajo (sobreventa agresiva)
        df.loc[df['rsi'] < self.oversold, 'signal'] = self.SIGNAL_BUY
        
        # SHORT: RSI extremadamente alto (sobrecompra agresiva)
        df.loc[df['rsi'] > self.overbought, 'signal'] = self.SIGNAL_SELL
        
        return df

    def get_features(self):
        return ['rsi', 'roc']