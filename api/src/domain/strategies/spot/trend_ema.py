import pandas as pd
import numpy as np
from typing import List, Dict, Any, Optional
from api.src.domain.strategies.base import BaseStrategy

class TrendEma(BaseStrategy):
    """
    Trend EMA Strategy v2.0 - Optimized
    
    Seguimiento de tendencia con múltiples EMAs y filtros de confirmación.
    
    Mejoras aplicadas:
    - Triple EMA (9/21/50) para confirmación de tendencia
    - ADX filtro (fuerza de tendencia)
    - Volumen relativo para confirmación
    - EMA slope (pendiente) como feature
    - Pullback detection (entrada en retroceso)
    """
    
    def __init__(self, config=None):
        super().__init__(config or {})
        self.ema_fast = int(self.config.get('ema_fast', 9))
        self.ema_mid = int(self.config.get('ema_mid', 21))
        self.ema_slow = int(self.config.get('ema_slow', 50))
        self.adx_period = int(self.config.get('adx_period', 14))
        self.vol_ma = int(self.config.get('vol_ma', 20))
        self.adx_threshold = float(self.config.get('adx_threshold', 25))

    def apply(self, df: pd.DataFrame, current_position: dict = None) -> pd.DataFrame:
        if len(df) < self.ema_slow + self.adx_period:
            df['signal'] = self.SIGNAL_WAIT
            return df

        # 1. Triple EMA
        df['ema_f'] = df['close'].ewm(span=self.ema_fast, adjust=False).mean()
        df['ema_m'] = df['close'].ewm(span=self.ema_mid, adjust=False).mean()
        df['ema_s'] = df['close'].ewm(span=self.ema_slow, adjust=False).mean()
        
        # 2. EMA differences (features para ML)
        df['ema_diff_fm'] = (df['ema_f'] - df['ema_m']) / df['ema_m'] * 100
        df['ema_diff_ms'] = (df['ema_m'] - df['ema_s']) / df['ema_s'] * 100
        df['ema_diff_fs'] = (df['ema_f'] - df['ema_s']) / df['ema_s'] * 100
        
        # 3. EMA slope (pendiente = fuerza de tendencia)
        df['ema_f_slope'] = df['ema_f'].pct_change(5) * 100
        df['ema_m_slope'] = df['ema_m'].pct_change(5) * 100
        
        # 4. ADX (Average Directional Index) - fuerza de tendencia
        # +DM y -DM
        df['high_diff'] = df['high'].diff()
        df['low_diff'] = df['low'].diff()
        df['plus_dm'] = np.where((df['high_diff'] > abs(df['low_diff'])) & (df['high_diff'] > 0), df['high_diff'], 0)
        df['minus_dm'] = np.where((abs(df['low_diff']) > df['high_diff']) & (df['low_diff'] < 0), abs(df['low_diff']), 0)
        
        # TR
        df['tr'] = pd.concat([df['high'] - df['low'], 
                             (df['high'] - df['close'].shift()).abs(), 
                             (df['low'] - df['close'].shift()).abs()], axis=1).max(axis=1)
        
        # Suavizado
        df['tr_smooth'] = df['tr'].rolling(self.adx_period).sum()
        df['plus_di'] = 100 * df['plus_dm'].rolling(self.adx_period).sum() / (df['tr_smooth'] + 1e-10)
        df['minus_di'] = 100 * df['minus_dm'].rolling(self.adx_period).sum() / (df['tr_smooth'] + 1e-10)
        df['dx'] = 100 * abs(df['plus_di'] - df['minus_di']) / (df['plus_di'] + df['minus_di'] + 1e-10)
        df['adx'] = df['dx'].rolling(self.adx_period).mean()
        
        # 5. Volumen relativo
        df['vol_ma'] = df['volume'].rolling(window=self.vol_ma).mean()
        df['vol_ratio'] = df['volume'] / df['vol_ma']
        
        # 6. Tendencia alineada (todas EMAs en orden)
        df['trend_aligned_bull'] = (df['ema_f'] > df['ema_m']) & (df['ema_m'] > df['ema_s'])
        df['trend_aligned_bear'] = (df['ema_f'] < df['ema_m']) & (df['ema_m'] < df['ema_s'])
        
        # 7. Pullback detection (precio retrocede a EMA media en tendencia alcista)
        df['pullback_bull'] = df['trend_aligned_bull'] & (df['close'] <= df['ema_m']) & (df['close'] > df['ema_s'])
        df['pullback_bear'] = df['trend_aligned_bear'] & (df['close'] >= df['ema_m']) & (df['close'] < df['ema_s'])

        df['signal'] = self.SIGNAL_WAIT
        
        # COMPRA: Tendencia alcista alineada + ADX > threshold + volumen
        buy_trend = df['trend_aligned_bull'] | df['pullback_bull']
        buy_adx = df['adx'] > self.adx_threshold
        buy_vol = df['vol_ratio'] > 1.0
        
        df.loc[buy_trend & buy_adx & buy_vol, 'signal'] = self.SIGNAL_BUY

        # VENTA: Tendencia bajista alineada + ADX > threshold + volumen
        sell_trend = df['trend_aligned_bear'] | df['pullback_bear']
        sell_adx = df['adx'] > self.adx_threshold
        sell_vol = df['vol_ratio'] > 1.0
        
        df.loc[sell_trend & sell_adx & sell_vol, 'signal'] = self.SIGNAL_SELL

        return df

    def on_price_tick(self, price: float, current_position: dict = None, context: dict = None) -> int:
        """
        Tick rápido: continuación de tendencia por ruptura.
        """
        if price is None or price <= 0:
            return self.SIGNAL_WAIT

        ctx = context or {}
        prev_price = float(ctx.get("prev_price") or 0)
        if prev_price <= 0:
            return self.SIGNAL_WAIT

        change = (float(price) - prev_price) / prev_price
        trigger = float(self.config.get("tick_trend_trigger_pct", 0.3)) / 100.0

        if current_position and float(current_position.get("qty", 0) or 0) > 0:
            return self.SIGNAL_WAIT

        if change >= trigger:
            return self.SIGNAL_BUY
        if change <= -trigger:
            return self.SIGNAL_SELL
            
        return self.SIGNAL_WAIT

    def get_features(self) -> List[str]:
        return ['ema_diff_fm', 'ema_diff_ms', 'ema_f_slope', 'adx', 'vol_ratio', 'trend_aligned_bull', 'trend_aligned_bear']
