import pandas as pd
import numpy as np
from typing import List, Dict, Any, Optional
from api.src.domain.strategies.base import BaseStrategy

class RsiReversion(BaseStrategy):
    """
    RSI Reversion Strategy v2.0 - Optimized
    
    Reversión a la media basada en RSI extremo con filtros de confirmación.
    
    Mejoras aplicadas:
    - RSI suavizado para reducir ruido
    - Divergencias RSI-precio
    - Filtro de tendencia (EMA 200)
    - Zonas dinámicas (ajustables por volatilidad)
    - Volumen para confirmación
    - Wick detection (mechas de agotamiento)
    """
    
    def __init__(self, config=None):
        super().__init__(config or {})
        self.rsi_period = int(self.config.get('rsi_period', 14))
        self.oversold = float(self.config.get('oversold', 25))
        self.overbought = float(self.config.get('overbought', 75))
        self.ema_trend = int(self.config.get('ema_trend', 200))
        self.vol_ma = int(self.config.get('vol_ma', 20))
        self.divergence_lookback = int(self.config.get('divergence_lookback', 5))

    def apply(self, df: pd.DataFrame, current_position: dict = None) -> pd.DataFrame:
        if len(df) < self.ema_trend:
            df['signal'] = self.SIGNAL_WAIT
            return df

        # 1. RSI calculation
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=self.rsi_period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=self.rsi_period).mean()
        rs = gain / (loss + 1e-10)
        df['rsi'] = 100 - (100 / (1 + rs))
        
        # 2. RSI suavizado
        df['rsi_smooth'] = df['rsi'].ewm(span=3, adjust=False).mean()
        
        # 3. RSI normalizado (para ML)
        df['rsi_norm'] = (df['rsi'] - df['rsi'].rolling(50).min()) / \
                        (df['rsi'].rolling(50).max() - df['rsi'].rolling(50).min() + 1e-10)
        
        # 4. Filtro de tendencia
        df['ema_200'] = df['close'].ewm(span=self.ema_trend, adjust=False).mean()
        df['trend'] = 1 if df['close'].iloc[-1] > df['ema_200'].iloc[-1] else -1
        
        # 5. Zonas dinámicas (ajustar por volatilidad)
        df['volatility'] = df['close'].rolling(20).std() / df['close'].rolling(20).mean()
        df['high_vol'] = df['volatility'] > df['volatility'].rolling(50).median()
        
        # En alta volatilidad: zonas más extremas (20/80)
        # En baja volatilidad: zonas normales (25/75)
        df['oversold_zone'] = np.where(df['high_vol'], 20, self.oversold)
        df['overbought_zone'] = np.where(df['high_vol'], 80, self.overbought)
        
        # 6. Volumen relativo
        df['vol_ma'] = df['volume'].rolling(window=self.vol_ma).mean()
        df['vol_ratio'] = df['volume'] / df['vol_ma']
        
        # 7. Divergencias
        df['price_min'] = df['close'].rolling(self.divergence_lookback).min()
        df['rsi_min'] = df['rsi'].rolling(self.divergence_lookback).min()
        df['bull_div'] = (df['close'] < df['price_min'].shift(1)) & (df['rsi'] > df['rsi_min'].shift(1))
        
        df['price_max'] = df['close'].rolling(self.divergence_lookback).max()
        df['rsi_max'] = df['rsi'].rolling(self.divergence_lookback).max()
        df['bear_div'] = (df['close'] > df['price_max'].shift(1)) & (df['rsi'] < df['rsi_max'].shift(1))
        
        # 8. Wick detection (mechas de agotamiento)
        df['wick_lower'] = (df['close'] - df['low']) > (df['high'] - df['close']) * 2
        df['wick_upper'] = (df['high'] - df['close']) > (df['close'] - df['low']) * 2
        
        # 9. RSI extremos
        df['rsi_extreme_low'] = df['rsi'] < df['oversold_zone']
        df['rsi_extreme_high'] = df['rsi'] > df['overbought_zone']
        
        # 10. Salida de zonas extremas
        df['exit_oversold'] = (df['rsi'] > df['oversold_zone']) & (df['rsi'].shift(1) <= df['oversold_zone'])
        df['exit_overbought'] = (df['rsi'] < df['overbought_zone']) & (df['rsi'].shift(1) >= df['overbought_zone'])

        df['signal'] = self.SIGNAL_WAIT
        
        # COMPRA: RSI extremo + (divergencia O mecha inferior) + volumen
        buy_extreme = df['rsi_extreme_low']
        buy_confirm = df['bull_div'] | df['wick_lower']
        buy_vol = df['vol_ratio'] > 0.8
        
        df.loc[buy_extreme & buy_confirm & buy_vol, 'signal'] = self.SIGNAL_BUY
        df.loc[df['exit_oversold'] & buy_vol & (df['trend'] >= 0), 'signal'] = self.SIGNAL_BUY

        # VENTA: RSI extremo + (divergencia O mecha superior) + volumen
        sell_extreme = df['rsi_extreme_high']
        sell_confirm = df['bear_div'] | df['wick_upper']
        sell_vol = df['vol_ratio'] > 0.8
        
        df.loc[sell_extreme & sell_confirm & sell_vol, 'signal'] = self.SIGNAL_SELL
        df.loc[df['exit_overbought'] & sell_vol & (df['trend'] <= 0), 'signal'] = self.SIGNAL_SELL

        return df

    def on_price_tick(self, price: float, current_position: dict = None, context: dict = None) -> int:
        """
        Tick rápido: reversión por spike extremo.
        """
        if price is None or price <= 0:
            return self.SIGNAL_WAIT

        ctx = context or {}
        prev_price = float(ctx.get("prev_price") or 0)
        if prev_price <= 0:
            return self.SIGNAL_WAIT

        change = (float(price) - prev_price) / prev_price
        spike = float(self.config.get("tick_reversion_spike_pct", 0.5)) / 100.0

        # Reversión: spike negativo → BUY, spike positivo → SELL
        if change <= -spike:
            return self.SIGNAL_BUY
        if change >= spike:
            return self.SIGNAL_SELL
            
        return self.SIGNAL_WAIT

    def get_features(self) -> List[str]:
        return ['rsi', 'rsi_smooth', 'rsi_norm', 'bull_div', 'bear_div', 'wick_lower', 'wick_upper']
