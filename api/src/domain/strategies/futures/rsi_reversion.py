import pandas as pd
from api.src.domain.strategies.base import BaseStrategy

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

    def on_price_tick(self, price: float, current_position: dict = None, context: dict = None) -> int:
        ctx = context or {}
        prev_price = float(ctx.get("prev_price") or 0)
        if price is None or price <= 0 or prev_price <= 0:
            return self.SIGNAL_WAIT

        change = (float(price) - prev_price) / prev_price
        spike = float(self.config.get("tick_reversion_spike_pct", 0.35)) / 100.0
        if change <= -spike:
            return self.SIGNAL_BUY
        if change >= spike:
            return self.SIGNAL_SELL
        return self.SIGNAL_WAIT

    def get_features(self):
        return ['rsi', 'roc']