# signal_tools/ta_calc.py
from __future__ import annotations
import numpy as np
import pandas as pd

# ---------------------------------------------------------------------
# Допоміжні
# ---------------------------------------------------------------------
def _ensure_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    """Приводимо назви колонок до нижнього регістру та перевіряємо наявність open/high/low/close/volume."""
    if df is None or df.empty:
        return pd.DataFrame(columns=["open","high","low","close","volume"])
    out = df.copy()
    out.columns = [str(c).lower() for c in out.columns]
    for col in ["open","high","low","close","volume"]:
        if col not in out.columns:
            out[col] = np.nan
    return out

def _ema(s: pd.Series, span: int) -> pd.Series:
    return s.ewm(span=span, adjust=False).mean()

def _sma(s: pd.Series, length: int) -> pd.Series:
    return s.rolling(length, min_periods=length).mean()

def _rsi(close: pd.Series, length: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/length, adjust=False, min_periods=length).mean()
    avg_loss = loss.ewm(alpha=1/length, adjust=False, min_periods=length).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi

def _macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> tuple[pd.Series, pd.Series, pd.Series]:
    ema_fast = _ema(close, fast)
    ema_slow = _ema(close, slow)
    macd = ema_fast - ema_slow
    macd_signal = _ema(macd, signal)
    macd_hist = macd - macd_signal
    return macd, macd_signal, macd_hist

def _true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs()
    ], axis=1).max(axis=1)
    return tr

def _atr(high: pd.Series, low: pd.Series, close: pd.Series, length: int = 14) -> pd.Series:
    tr = _true_range(high, low, close)
    # Wilder'ове згладжування еквівалентно EMA з alpha=1/n
    return tr.ewm(alpha=1/length, adjust=False, min_periods=length).mean()

def _stochrsi(close: pd.Series, rsi_len: int = 14, stoch_len: int = 14, k_len: int = 3, d_len: int = 3) -> tuple[pd.Series, pd.Series]:
    rsi = _rsi(close, rsi_len)
    rsi_min = rsi.rolling(stoch_len, min_periods=stoch_len).min()
    rsi_max = rsi.rolling(stoch_len, min_periods=stoch_len).max()
    stoch = (rsi - rsi_min) / (rsi_max - rsi_min).replace(0, np.nan)
    k = _sma(stoch, k_len)
    d = _sma(k, d_len)
    return k, d

def _bbands(close: pd.Series, length: int = 20, num_std: float = 2.0) -> tuple[pd.Series, pd.Series, pd.Series, pd.Series]:
    ma = _sma(close, length)
    std = close.rolling(length, min_periods=length).std()
    upper = ma + num_std * std
    lower = ma - num_std * std
    pct_b = (close - lower) / (upper - lower)
    return ma, upper, lower, pct_b

def _obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    change = close.diff()
    sign = np.where(change > 0, 1, np.where(change < 0, -1, 0))
    obv = (volume * sign).fillna(0).cumsum()
    return obv

def _mfi(high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series, length: int = 14) -> pd.Series:
    tp = (high + low + close) / 3.0
    rmf = tp * volume
    prev_tp = tp.shift(1)
    pos = rmf.where(tp > prev_tp, 0.0)
    neg = rmf.where(tp < prev_tp, 0.0)
    pos_sum = pos.rolling(length, min_periods=length).sum()
    neg_sum = neg.rolling(length, min_periods=length).sum()
    mr = pos_sum / neg_sum.replace(0, np.nan)
    mfi = 100 - (100 / (1 + mr))
    return mfi

def _adx(high: pd.Series, low: pd.Series, close: pd.Series, length: int = 14) -> pd.Series:
    # +DM / -DM
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
    plus_dm = pd.Series(plus_dm, index=high.index)
    minus_dm = pd.Series(minus_dm, index=high.index)

    tr = _true_range(high, low, close)

    atr = tr.ewm(alpha=1/length, adjust=False, min_periods=length).mean()
    plus_di = 100 * (plus_dm.ewm(alpha=1/length, adjust=False, min_periods=length).mean() / atr.replace(0, np.nan))
    minus_di = 100 * (minus_dm.ewm(alpha=1/length, adjust=False, min_periods=length).mean() / atr.replace(0, np.nan))

    dx = (100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan))
    adx = dx.ewm(alpha=1/length, adjust=False, min_periods=length).mean()
    return adx

def _cci(high: pd.Series, low: pd.Series, close: pd.Series, length: int = 14) -> pd.Series:
    tp = (high + low + close) / 3.0
    sma_tp = _sma(tp, length)
    md = (tp - sma_tp).abs().rolling(length, min_periods=length).mean()
    cci = (tp - sma_tp) / (0.015 * md.replace(0, np.nan))
    return cci

def _pivots_classic(prev_h: pd.Series, prev_l: pd.Series, prev_c: pd.Series):
    """Класичні pivot-рівні з попереднього бару (на кожен бар)"""
    p = (prev_h + prev_l + prev_c) / 3.0
    r1 = 2 * p - prev_l
    s1 = 2 * p - prev_h
    r2 = p + (prev_h - prev_l)
    s2 = p - (prev_h - prev_l)
    r3 = prev_h + 2 * (p - prev_l)
    s3 = prev_l - 2 * (prev_h - p)
    return p, r1, s1, r2, s2, r3, s3

def _pivots_fibonacci(prev_h: pd.Series, prev_l: pd.Series, prev_c: pd.Series):
    """Fibonacci pivot-рівні з попереднього бару (на кожен бар)"""
    p = (prev_h + prev_l + prev_c) / 3.0
    r = (prev_h - prev_l).abs()
    r1 = p + 0.382 * r
    s1 = p - 0.382 * r
    r2 = p + 0.618 * r
    s2 = p - 0.618 * r
    r3 = p + 1.000 * r
    s3 = p - 1.000 * r
    return p, r1, s1, r2, s2, r3, s3

# ---------------------------------------------------------------------
# Основна функція
# ---------------------------------------------------------------------
def get_ta_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Очікує DataFrame з колонками: open, high, low, close, volume (регістр неважливий).
    Повертає копію з доданими колонками:
      - sma_7, sma_25
      - ema_50, ema_200
      - macd, macd_signal
      - rsi
      - stochrsi_k, stochrsi_d
      - atr_14
      - bb_ma_20, bb_upper_20_2, bb_lower_20_2, pct_b
      - obv
      - mfi
      - adx
      - cci
      - pivot, r1, s1, r2, s2, r3, s3
      - fib_pivot, fib_r1, fib_s1, fib_r2, fib_s2, fib_r3, fib_s3
    """
    data = _ensure_ohlcv(df)
    out = data.copy()

    o, h, l, c, v = out["open"], out["high"], out["low"], out["close"], out["volume"]

    # Базові середні для /top
    out["sma_7"] = _sma(c, 7)
    out["sma_25"] = _sma(c, 25)

    # EMA тренд
    out["ema_50"] = _ema(c, 50)
    out["ema_200"] = _ema(c, 200)

    # MACD(12,26,9)
    macd, macd_signal, macd_hist = _macd(c, 12, 26, 9)
    out["macd"] = macd
    out["macd_signal"] = macd_signal
    # hist не використовуємо в інших частинах, але може знадобитись
    out["macd_hist"] = macd_hist

    # RSI(14)
    out["rsi"] = _rsi(c, 14)

    # StochRSI(14,14,3,3)
    k, d_ = _stochrsi(c, 14, 14, 3, 3)
    out["stochrsi_k"] = k
    out["stochrsi_d"] = d_

    # ATR(14)
    out["atr_14"] = _atr(h, l, c, 14)

    # Bollinger Bands(20, 2σ) + %B
    bb_ma, bb_up, bb_lo, pct_b = _bbands(c, 20, 2.0)
    out["bb_ma_20"] = bb_ma
    out["bb_upper_20_2"] = bb_up
    out["bb_lower_20_2"] = bb_lo
    out["pct_b"] = pct_b

    # OBV
    out["obv"] = _obv(c, v)

    # MFI(14)
    out["mfi"] = _mfi(h, l, c, v, 14)

    # ADX(14)
    out["adx"] = _adx(h, l, c, 14)

    # CCI(14)
    out["cci"] = _cci(h, l, c, 14)

    # Pivot-и з попереднього бару
    prev_h, prev_l, prev_c = h.shift(1), l.shift(1), c.shift(1)

    p, r1, s1, r2, s2, r3, s3 = _pivots_classic(prev_h, prev_l, prev_c)
    out["pivot"] = p
    out["r1"] = r1
    out["s1"] = s1
    out["r2"] = r2
    out["s2"] = s2
    out["r3"] = r3
    out["s3"] = s3

    fp, fr1, fs1, fr2, fs2, fr3, fs3 = _pivots_fibonacci(prev_h, prev_l, prev_c)
    out["fib_pivot"] = fp
    out["fib_r1"] = fr1
    out["fib_s1"] = fs1
    out["fib_r2"] = fr2
    out["fib_s2"] = fs2
    out["fib_r3"] = fr3
    out["fib_s3"] = fs3

    return out
