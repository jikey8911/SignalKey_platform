import pandas as pd
import numpy as np

def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()

def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.ewm(alpha=1/period, adjust=False).mean()

def adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    up = high - high.shift()
    down = low.shift() - low
    
    pos_dm = np.where((up > down) & (up > 0), up, 0.0)
    neg_dm = np.where((down > up) & (down > 0), down, 0.0)
    
    tr = atr(high, low, close, period)
    
    # Smooth DM using similar alpha to ATR
    pos_dm_s = pd.Series(pos_dm, index=high.index).ewm(alpha=1/period, adjust=False).mean()
    neg_dm_s = pd.Series(neg_dm, index=high.index).ewm(alpha=1/period, adjust=False).mean()
    
    # Avoid div by zero
    pos_di = 100 * (pos_dm_s / tr.replace(0, 1))
    neg_di = 100 * (neg_dm_s / tr.replace(0, 1))
    
    dx = 100 * (abs(pos_di - neg_di) / (pos_di + neg_di).replace(0, 1))
    return dx.ewm(alpha=1/period, adjust=False).mean() # ADX is smoothed DX

def bollinger_bands(close: pd.Series, period: int = 20, std_dev: float = 2.0) -> pd.DataFrame:
    sma = close.rolling(window=period).mean()
    std = close.rolling(window=period).std()
    upper = sma + (std * std_dev)
    lower = sma - (std * std_dev)
    return pd.DataFrame({'upper': upper, 'mid': sma, 'lower': lower})

def donchian(high: pd.Series, low: pd.Series, period: int) -> pd.DataFrame:
    upper = high.rolling(window=period).max()
    lower = low.rolling(window=period).min()
    mid = (upper + lower) / 2
    return pd.DataFrame({'upper': upper, 'mid': mid, 'lower': lower})
