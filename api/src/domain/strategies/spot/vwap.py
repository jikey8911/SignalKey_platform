import numpy as np
import pandas as pd
from typing import List, Dict, Any, Optional
from api.src.domain.strategies.base import BaseStrategy

class VWAPStrategy(BaseStrategy):
    """
    VWAP Strategy v2.0 - Optimized
    
    Volume Weighted Average Price con bandas y filtros de confirmación.
    
    Mejoras aplicadas:
    - VWAP anclado (reset diario simulado)
    - Bandas de desviación estándar (±1σ, ±2σ)
    - Filtro de tendencia (EMA 200)
    - Volumen relativo para confirmación
    - VWAP slope como feature
    - Mean reversion a VWAP
    """
    
    def __init__(self, config=None):
        super().__init__(config or {})
        self.std_period = int(self.config.get('std_period', 20))
        self.std_multiplier = float(self.config.get('std_multiplier', 2.0))
        self.ema_trend = int(self.config.get('ema_trend', 200))
        self.vol_ma = int(self.config.get('vol_ma', 20))

    def apply(self, df: pd.DataFrame, current_position: dict = None) -> pd.DataFrame:
        if len(df) < self.ema_trend:
            df['signal'] = self.SIGNAL_WAIT
            return df

        # 1. VWAP calculation (cumulativo con reset simulado cada N periodos)
        # En producción real, resetear cada día. Aquí usamos rolling VWAP.
        typical_price = (df['high'] + df['low'] + df['close']) / 3
        cum_vol = df['volume'].rolling(window=self.std_period).sum()
        cum_vol_price = (typical_price * df['volume']).rolling(window=self.std_period).sum()
        df['vwap'] = cum_vol_price / (cum_vol + 1e-10)
        
        # 2. VWAP bands (desviación estándar)
        df['vwap_std'] = df['close'].rolling(window=self.std_period).std()
        df['vwap_upper1'] = df['vwap'] + (1 * df['vwap_std'])
        df['vwap_lower1'] = df['vwap'] - (1 * df['vwap_std'])
        df['vwap_upper2'] = df['vwap'] + (self.std_multiplier * df['vwap_std'])
        df['vwap_lower2'] = df['vwap'] - (self.std_multiplier * df['vwap_std'])
        
        # 3. Posición relativa a VWAP
        df['vwap_position'] = (df['close'] - df['vwap']) / df['vwap'] * 100
        df['vwap_normalized'] = (df['close'] - df['vwap']) / (df['vwap_std'] + 1e-10)
        
        # 4. VWAP slope (tendencia)
        df['vwap_slope'] = df['vwap'].pct_change(5) * 100
        df['vwap_slope_sign'] = np.sign(df['vwap_slope'])
        
        # 5. Filtro de tendencia
        df['ema_200'] = df['close'].ewm(span=self.ema_trend, adjust=False).mean()
        df['trend'] = 1 if df['close'].iloc[-1] > df['ema_200'].iloc[-1] else -1
        
        # 6. Volumen relativo
        df['vol_ma'] = df['volume'].rolling(window=self.vol_ma).mean()
        df['vol_ratio'] = df['volume'] / df['vol_ma']
        
        # 7. Mean reversion signal
        df['mean_rev'] = abs(df['vwap_normalized']) > 1.5  # Más de 1.5σ de VWAP
        
        # 8. Cruces de VWAP
        df['vwap_cross_up'] = (df['close'] > df['vwap']) & (df['close'].shift(1) <= df['vwap'].shift(1))
        df['vwap_cross_down'] = (df['close'] < df['vwap']) & (df['close'].shift(1) >= df['vwap'].shift(1))
        
        # 9. Confirmación de cruces
        df['vwap_cross_up_confirmed'] = df['vwap_cross_up'] & (df['vol_ratio'] > 1.0)
        df['vwap_cross_down_confirmed'] = df['vwap_cross_down'] & (df['vol_ratio'] > 1.0)

        df['signal'] = self.SIGNAL_WAIT
        
        # COMPRA: Cruce VWAP confirmado + (tendencia favorable O mean reversion desde abajo)
        buy_trend = (df['trend'] >= 0) | (df['vwap_normalized'] < -1.5)
        buy_vol = df['vol_ratio'] > 0.8
        
        df.loc[df['vwap_cross_up_confirmed'] & buy_trend & buy_vol, 'signal'] = self.SIGNAL_BUY
        
        # COMPRA alternativa: Mean reversion extrema (precio < VWAP - 2σ)
        df.loc[(df['close'] < df['vwap_lower2']) & (df['vol_ratio'] > 1.2), 'signal'] = self.SIGNAL_BUY

        # VENTA: Cruce VWAP confirmado + (tendencia favorable O mean reversion desde arriba)
        sell_trend = (df['trend'] <= 0) | (df['vwap_normalized'] > 1.5)
        sell_vol = df['vol_ratio'] > 0.8
        
        df.loc[df['vwap_cross_down_confirmed'] & sell_trend & sell_vol, 'signal'] = self.SIGNAL_SELL
        
        # VENTA alternativa: Mean reversion extrema (precio > VWAP + 2σ)
        df.loc[(df['close'] > df['vwap_upper2']) & (df['vol_ratio'] > 1.2), 'signal'] = self.SIGNAL_SELL

        return df

    def on_price_tick(self, price: float, current_position: dict = None, context: dict = None) -> int:
        """
        Tick intravela: detector de desviación extrema de VWAP.
        """
        if price is None or price <= 0:
            return self.SIGNAL_WAIT

        ctx = context or {}
        prev_price = float(ctx.get("prev_price") or 0)
        vwap = float(ctx.get("vwap") or price)
        
        if prev_price <= 0 or vwap <= 0:
            return self.SIGNAL_WAIT

        change = (float(price) - prev_price) / prev_price
        vwap_dev = (float(price) - vwap) / vwap * 100
        trigger = float(self.config.get("tick_vwap_trigger_pct", 0.5)) / 100.0
        vwap_trigger = float(self.config.get("tick_vwap_dev_pct", 1.0)) / 100.0

        if current_position and float(current_position.get("qty", 0) or 0) > 0:
            return self.SIGNAL_WAIT

        # Ruptura o reversión extrema
        if change >= trigger:
            return self.SIGNAL_BUY
        if change <= -trigger:
            return self.SIGNAL_SELL
        if vwap_dev <= -vwap_trigger:  # Precio muy por debajo de VWAP
            return self.SIGNAL_BUY
        if vwap_dev >= vwap_trigger:  # Precio muy por encima de VWAP
            return self.SIGNAL_SELL
            
        return self.SIGNAL_WAIT

    def get_features(self) -> List[str]:
        return ['vwap_position', 'vwap_normalized', 'vwap_slope', 'vwap_cross_up_confirmed', 'vwap_cross_down_confirmed', 'mean_rev']
