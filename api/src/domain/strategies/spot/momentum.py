import numpy as np
import pandas as pd
from typing import List, Dict, Any, Optional
from api.src.domain.strategies.base import BaseStrategy

class MomentumStrategy(BaseStrategy):
    """
    Momentum Strategy v2.0 - Optimized
    
    Mide la velocidad del cambio de precio con filtros de confirmación.
    
    Mejoras aplicadas:
    - ROC suavizado con EMA para reducir ruido
    - Filtro de volumen (confirmación de fuerza)
    - Filtro de tendencia (EMA 200) para evitar señales contra-tendencia
    - Divergencia de momentum para early signals
    - Tick handler optimizado para intravela
    """
    
    def __init__(self, config=None):
        super().__init__(config or {})
        self.roc_period = int(self.config.get('roc_period', 10))
        self.roc_smooth = int(self.config.get('roc_smooth', 3))
        self.vol_ma = int(self.config.get('vol_ma', 20))
        self.ema_trend = int(self.config.get('ema_trend', 200))
        self.momentum_threshold = float(self.config.get('momentum_threshold', 0))

    def apply(self, df: pd.DataFrame, current_position: dict = None) -> pd.DataFrame:
        if len(df) < self.ema_trend:
            df['signal'] = self.SIGNAL_WAIT
            return df

        # 1. ROC suavizado (menos ruido que ROC simple)
        df['roc_raw'] = ((df['close'] / df['close'].shift(self.roc_period)) - 1) * 100
        df['roc'] = df['roc_raw'].ewm(span=self.roc_smooth, adjust=False).mean()
        
        # 2. Filtro de volumen (confirmación)
        df['vol_ma'] = df['volume'].rolling(window=self.vol_ma).mean()
        df['vol_ratio'] = df['volume'] / df['vol_ma']
        
        # 3. Filtro de tendencia macro
        df['ema_200'] = df['close'].ewm(span=self.ema_trend, adjust=False).mean()
        df['trend'] = 1 if df['close'].iloc[-1] > df['ema_200'].iloc[-1] else -1
        
        # 4. Divergencia de momentum (feature avanzada)
        df['roc_diff'] = df['roc'].diff()
        
        # 5. Normalized momentum (0-100 scale)
        df['momentum_norm'] = ((df['roc'] - df['roc'].rolling(50).min()) / 
                               (df['roc'].rolling(50).max() - df['roc'].rolling(50).min() + 1e-9)) * 100

        df['signal'] = self.SIGNAL_WAIT
        
        # COMPRA: ROC cruza de negativo a positivo + volumen confirm + tendencia alcista o neutra
        buy_cross = (df['roc'] > self.momentum_threshold) & (df['roc'].shift(1) <= self.momentum_threshold)
        buy_vol = df['vol_ratio'] > 1.0
        buy_trend = (df['trend'] >= 0) | (df['roc'] > 2.0)  # Momentum fuerte puede ignorar tendencia
        
        df.loc[buy_cross & buy_vol & buy_trend, 'signal'] = self.SIGNAL_BUY

        # VENTA: ROC cruza de positivo a negativo + volumen confirm + tendencia bajista o neutra
        sell_cross = (df['roc'] < self.momentum_threshold) & (df['roc'].shift(1) >= self.momentum_threshold)
        sell_vol = df['vol_ratio'] > 1.0
        sell_trend = (df['trend'] <= 0) | (df['roc'] < -2.0)
        
        df.loc[sell_cross & sell_vol & sell_trend, 'signal'] = self.SIGNAL_SELL

        return df

    def on_price_tick(self, price: float, current_position: dict = None, context: dict = None) -> int:
        """
        Tick intravela: detector de aceleración brusca con filtro de posición.
        """
        if price is None or price <= 0:
            return self.SIGNAL_WAIT

        ctx = context or {}
        prev_price = float(ctx.get("prev_price") or 0)
        if prev_price <= 0:
            return self.SIGNAL_WAIT

        change = (float(price) - prev_price) / prev_price
        spike_pct = float(self.config.get("tick_spike_pct", 0.6)) / 100.0
        
        # Si ya hay posición, no entramos en contra
        if current_position and float(current_position.get("qty", 0) or 0) > 0:
            return self.SIGNAL_WAIT

        if change >= spike_pct:
            return self.SIGNAL_BUY
        if change <= -spike_pct:
            return self.SIGNAL_SELL
            
        return self.SIGNAL_WAIT

    def get_features(self) -> List[str]:
        return ['roc', 'vol_ratio', 'momentum_norm', 'roc_diff']
