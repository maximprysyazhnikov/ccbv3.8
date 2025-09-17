from __future__ import annotations
import numpy as np
import pandas as pd

def _ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()

def ema(series: pd.Series, n: int) -> pd.Series:
    return _ema(series.astype(float), n)

def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    h = df["high"].astype(float)
    l = df["low"].astype(float)
    c = df["close"].astype(float)
    prev_c = c.shift(1)
    tr = pd.concat([(h - l), (h - prev_c).abs(), (l - prev_c).abs()], axis=1).max(axis=1)
    return tr.rolling(n, min_periods=n).mean()

def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    c = close.astype(float)
    delta = c.diff()
    up = delta.clip(lower=0)
    dn = -delta.clip(upper=0)
    roll_up = up.rolling(n, min_periods=n).mean()
    roll_dn = dn.rolling(n, min_periods=n).mean()
    rs = roll_up / (roll_dn.replace(0, np.nan))
    out = 100 - (100 / (1 + rs))
    return out.fillna(50.0)

def _dm(df: pd.DataFrame):
    up_move = df["high"].diff()
    down_move = -df["low"].diff()
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
    return pd.Series(plus_dm, index=df.index), pd.Series(minus_dm, index=df.index)

def adx(df: pd.DataFrame, n: int = 14) -> pd.Series:
    tr = atr(df, n) * 1.0
    plus_dm, minus_dm = _dm(df)
    atr_raw = pd.concat([
        (df["high"] - df["low"]),
        (df["high"] - df["close"].shift(1)).abs(),
        (df["low"] - df["close"].shift(1)).abs()
    ], axis=1).max(axis=1)
    atr_n = atr_raw.rolling(n, min_periods=n).mean()
    plus_di = 100 * (plus_dm.rolling(n, min_periods=n).sum() / atr_n)
    minus_di = 100 * (minus_dm.rolling(n, min_periods=n).sum() / atr_n)
    dx = ( (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan) ) * 100
    return dx.rolling(n, min_periods=n).mean().fillna(0.0)

def bbands(close: pd.Series, n: int = 20, k: float = 2.0):
    c = close.astype(float)
    ma = c.rolling(n, min_periods=n).mean()
    sd = c.rolling(n, min_periods=n).std(ddof=0)
    upper = ma + k * sd
    lower = ma - k * sd
    width = (upper - lower)
    return upper, ma, lower, width

def vwap(df: pd.DataFrame) -> pd.Series:
    tp = (df["high"] + df["low"] + df["close"]) / 3.0
    vol = df.get("volume")
    if vol is None:
        vol = pd.Series(np.ones(len(df)), index=df.index)
    pv = tp * vol
    cum_pv = pv.cumsum()
    cum_vol = vol.replace(0, np.nan).cumsum()
    return (cum_pv / cum_vol).fillna(method="ffill").fillna(tp)
