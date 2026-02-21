import pandas as pd
import numpy as np
from typing import List, Dict, Any
from api.src.domain.strategies.base import BaseStrategy

class SniperStrategy(BaseStrategy):
    """
    Estrategia Sniper v2.0 (Híbrida Spot/Futuros)
    
    Busca entradas de alta precisión basadas en:
    1. Reversión a la media (RSI) a favor de la tendencia (EMA 200).
    2. Volatilidad controlada (ATR).
    
    Características Futuros:
    - Apalancamiento Dinámico (inverso a volatilidad).
    - Stop Loss y Take Profit automáticos basados en ATR (Ratio 1:2).
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config or {})
        self.rsi_period = int(self.config.get('rsi_period', 14))
        self.rsi_overbought = float(self.config.get('rsi_overbought', 70.0))
        self.rsi_oversold = float(self.config.get('rsi_oversold', 30.0))
        self.ema_trend = int(self.config.get('ema_trend', 200))
        self.atr_period = int(self.config.get('atr_period', 14))
        
        # Futuros defaults
        self.leverage_base = float(self.config.get('leverage_base', 10.0))

    def apply(self, df: pd.DataFrame, current_position: dict = None) -> pd.DataFrame:
        if df.empty:
            return df

        # --- 1. Indicadores Técnicos ---
        
        # RSI
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=self.rsi_period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=self.rsi_period).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))

        # Tendencia (EMA 200)
        df['ema_trend'] = df['close'].ewm(span=self.ema_trend, adjust=False).mean()

        # Volatilidad (ATR)
        high_low = df['high'] - df['low']
        high_close = (df['high'] - df['close'].shift()).abs()
        low_close = (df['low'] - df['close'].shift()).abs()
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = ranges.max(axis=1)
        df['atr'] = true_range.rolling(self.atr_period).mean()

        # Features Normalizadas para ML
        df['rsi_norm'] = df['rsi'] / 100.0
        df['dist_ema'] = (df['close'] - df['ema_trend']) / df['close']
        df['atr_pct'] = (df['atr'] / df['close']) * 100

        # --- 2. Lógica de Señales (Sniper) ---
        df['signal'] = self.SIGNAL_WAIT
        
        # Definición de Tendencia
        trend_bullish = df['close'] > df['ema_trend']
        trend_bearish = df['close'] < df['ema_trend']
        
        # SNIPER LONG:
        # - Tendencia Alcista (Macro)
        # - Pullback profundo (RSI < 30)
        # - Confirmación de giro (RSI > RSI anterior)
        buy_cond = (
            trend_bullish & 
            (df['rsi'] < self.rsi_oversold) & 
            (df['rsi'] > df['rsi'].shift(1))
        )
        
        # SNIPER SHORT:
        # - Tendencia Bajista (Macro)
        # - Rally extendido (RSI > 70)
        # - Confirmación de giro (RSI < RSI anterior)
        sell_cond = (
            trend_bearish & 
            (df['rsi'] > self.rsi_overbought) & 
            (df['rsi'] < df['rsi'].shift(1))
        )
        
        df.loc[buy_cond, 'signal'] = self.SIGNAL_BUY
        df.loc[sell_cond, 'signal'] = self.SIGNAL_SELL
        
        # Limpieza de datos
        df.fillna(0, inplace=True)
        
        return df

    def get_trade_params(self, row: pd.Series, market_type: str = 'spot') -> Dict[str, Any]:
        """
        Calcula parámetros de ejecución avanzados para Futuros.
        """
        params = super().get_trade_params(row, market_type)
        
        # Solo aplicar lógica extra si es Futuros
        if market_type == 'futures':
            atr = float(row.get('atr', 0))
            close = float(row.get('close', 1))
            
            # 1. Apalancamiento Dinámico (Inverse Volatility Scaling)
            # Menor volatilidad -> Mayor apalancamiento
            # Mayor volatilidad -> Menor apalancamiento
            atr_pct = (atr / close) * 100
            
            leverage = self.leverage_base
            if atr_pct > 1.5:       # Muy volátil (>1.5% mov por vela)
                leverage = 3        # Conservador
            elif atr_pct < 0.5:     # Poco volátil (<0.5% mov por vela)
                leverage = 20       # Agresivo
            else:
                leverage = 10       # Estándar
            
            params['leverage'] = int(leverage)
            
            # 2. Stop Loss & Take Profit (ATR Based)
            # Ratio Riesgo:Beneficio = 1:2
            # SL = 2 * ATR
            # TP = 4 * ATR
            
            risk_dist = atr * 2.0
            reward_dist = atr * 4.0
            
            if row['signal'] == self.SIGNAL_BUY:
                params['sl'] = close - risk_dist
                params['tp'] = [{'price': close + reward_dist, 'qty': 1.0}]
                
            elif row['signal'] == self.SIGNAL_SELL:
                params['sl'] = close + risk_dist
                params['tp'] = [{'price': close - reward_dist, 'qty': 1.0}]

        return params

    def get_features(self) -> List[str]:
        return ['rsi_norm', 'dist_ema', 'atr_pct']
