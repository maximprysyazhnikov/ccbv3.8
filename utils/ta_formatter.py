from __future__ import annotations
import math
from typing import Dict
import pandas as pd
import numpy as np

from market_data.candles import get_ohlcv

# =========================
# ---- TA CALCULATIONS ----
# =========================

def _ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()

def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = np.where(delta > 0, delta, 0.0)
    loss = np.where(delta < 0, -delta, 0.0)
    gain = pd.Series(gain, index=close.index)
    loss = pd.Series(loss, index=close.index)
    avg_gain = gain.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    rs = avg_gain / (avg_loss.replace(0, np.nan))
    rsi = 100 - (100 / (1 + rs))
    return rsi.bfill()

def _macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    ema_fast = _ema(close, fast)
    ema_slow = _ema(close, slow)
    macd = ema_fast - ema_slow
    macd_signal = _ema(macd, signal)
    macd_hist = macd - macd_signal
    return macd, macd_signal, macd_hist

def _stochrsi(close: pd.Series, period: int = 14, k_period: int = 3, d_period: int = 3):
    rsi = _rsi(close, period)
    min_rsi = rsi.rolling(period).min()
    max_rsi = rsi.rolling(period).max()
    stoch_rsi = (rsi - min_rsi) / (max_rsi - min_rsi)
    k = stoch_rsi.rolling(k_period).mean()
    d = k.rolling(d_period).mean()
    return (k * 100).clip(0, 100), (d * 100).clip(0, 100)

def _true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat([
        (high - low),
        (high - prev_close).abs(),
        (low - prev_close).abs()
    ], axis=1).max(axis=1)
    return tr

def _atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    tr = _true_range(high, low, close)
    return tr.ewm(alpha=1/period, adjust=False, min_periods=period).mean()

def _adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    up_move = high.diff()
    down_move = -low.diff()

    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
    plus_dm = pd.Series(plus_dm, index=high.index)
    minus_dm = pd.Series(minus_dm, index=high.index)

    tr = _true_range(high, low, close)
    atr = tr.ewm(alpha=1/period, adjust=False, min_periods=period).mean()

    plus_di = 100 * (plus_dm.ewm(alpha=1/period, adjust=False).mean() / atr)
    minus_di = 100 * (minus_dm.ewm(alpha=1/period, adjust=False).mean() / atr)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
    adx = dx.ewm(alpha=1/period, adjust=False, min_periods=period).mean()
    return adx

def _cci(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 20) -> pd.Series:
    tp = (high + low + close) / 3
    sma_tp = tp.rolling(period).mean()
    mad = (tp - sma_tp).abs().rolling(period).mean()
    cci = (tp - sma_tp) / (0.015 * mad)
    return cci

def _bb(close: pd.Series, period: int = 20, std_mult: float = 2.0):
    ma = close.rolling(period).mean()
    sd = close.rolling(period).std()
    upper = ma + std_mult * sd
    lower = ma - std_mult * sd
    pct_b = (close - lower) / (upper - lower)
    return upper, ma, lower, pct_b

def _obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    direction = np.sign(close.diff()).fillna(0)
    return (volume * direction).cumsum()

def _mfi(high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series, period: int = 14) -> pd.Series:
    tp = (high + low + close) / 3
    mf = tp * volume
    pos_mf = mf.where(tp > tp.shift(1), 0.0)
    neg_mf = mf.where(tp < tp.shift(1), 0.0)
    pos_roll = pos_mf.rolling(period).sum()
    neg_roll = neg_mf.rolling(period).sum().replace(0, np.nan)
    mfr = pos_roll / neg_roll
    mfi = 100 - (100 / (1 + mfr))
    return mfi

def _pivots(prev_high: float, prev_low: float, prev_close: float) -> Dict[str, float]:
    p = (prev_high + prev_low + prev_close) / 3.0
    r1 = 2*p - prev_low
    s1 = 2*p - prev_high
    r2 = p + (prev_high - prev_low)
    s2 = p - (prev_high - prev_low)
    r3 = prev_high + 2*(p - prev_low)
    s3 = prev_low - 2*(prev_high - p)
    return {"pivot": p, "r1": r1, "s1": s1, "r2": r2, "s2": s2, "r3": r3, "s3": s3}

# =========================
# ---- REPORT FORMATTER ---
# =========================

def _fmt(x, d=2, dash="-"):
    try:
        v = float(x)
        if math.isnan(v) or math.isinf(v):
            return dash
        s = f"{v:,.{d}f}"
        return s.replace(",", " ")
    except Exception:
        return dash

def _badge(val: float, pos: str = "↑", neg: str = "↓", mid: str = "→", thr_lo: float = 45, thr_hi: float = 55):
    try:
        if val >= thr_hi: return f"{pos}"
        if val <= thr_lo: return f"{neg}"
        return f"{mid}"
    except Exception:
        return "·"

def format_ta_report(symbol: str, timeframe: str, limit: int = 150) -> str:
    """
    Формує красивий Markdown-блок по 12 індикаторах:
    RSI, MACD, StochRSI, ADX, CCI, ATR, Bollinger (%B), OBV, MFI, EMA/SMA, Pivots, Volume.
    """
    raw = get_ohlcv(symbol, timeframe, limit)
    if not raw:
        return "_No OHLCV data_"

    df = pd.DataFrame(raw)
    # очікувані колонки: ts, open, high, low, close, volume
    df = df.rename(columns={"ts": "timestamp"})
    df = df.dropna().reset_index(drop=True)

    close = df["close"]
    high = df["high"]
    low = df["low"]
    volume = df["volume"]

    # 1) RSI
    rsi = _rsi(close, 14)

    # 2) MACD
    macd, macd_sig, macd_hist = _macd(close)

    # 3) StochRSI %K/%D
    k, d = _stochrsi(close)

    # 4) ADX
    adx = _adx(high, low, close, 14)

    # 5) CCI
    cci = _cci(high, low, close, 20)

    # 6) ATR
    atr = _atr(high, low, close, 14)
    atr_pct = (atr / close) * 100

    # 7) Bollinger Bands (та %B)
    bb_u, bb_m, bb_l, pct_b = _bb(close)

    # 8) OBV
    obv = _obv(close, volume)

    # 9) MFI
    mfi = _mfi(high, low, close, volume, 14)

    # 10) EMA/SMA
    ema50 = _ema(close, 50)
    ema200 = _ema(close, 200)
    sma7 = close.rolling(7).mean()
    sma25 = close.rolling(25).mean()

    # 11) Pivots (за попередню свічку)
    if len(df) >= 2:
        prev = df.iloc[-2]
    else:
        prev = df.iloc[-1]
    piv = _pivots(prev_high=prev["high"], prev_low=prev["low"], prev_close=prev["close"])

    # 12) Volume summary
    vol_avg = volume.rolling(20).mean()
    vol_ratio = (volume.iloc[-1] / vol_avg.iloc[-1]) if vol_avg.iloc[-1] else np.nan

    # ---------- останні значення ----------
    last = len(df) - 1
    vals = {
        "price": close.iloc[-1],
        "rsi": rsi.iloc[-1],
        "macd": macd.iloc[-1],
        "macd_sig": macd_sig.iloc[-1],
        "macd_hist": macd_hist.iloc[-1],
        "stoch_k": k.iloc[-1],
        "stoch_d": d.iloc[-1],
        "adx": adx.iloc[-1],
        "cci": cci.iloc[-1],
        "atr": atr.iloc[-1],
        "atr_pct": atr_pct.iloc[-1],
        "pct_b": pct_b.iloc[-1],
        "obv": obv.iloc[-1],
        "mfi": mfi.iloc[-1],
        "ema50": ema50.iloc[-1],
        "ema200": ema200.iloc[-1],
        "sma7": sma7.iloc[-1],
        "sma25": sma25.iloc[-1],
        "pivot": piv["pivot"],
        "r1": piv["r1"], "s1": piv["s1"],
        "r2": piv["r2"], "s2": piv["s2"],
        "r3": piv["r3"], "s3": piv["s3"],
        "vol": volume.iloc[-1],
        "vol_ratio": vol_ratio,
    }

    # ---------- емодзі/бейджі ----------
    bias_trend = "🟢" if vals["ema50"] > vals["ema200"] else "🔴" if vals["ema50"] < vals["ema200"] else "⚪️"
    bias_macd = "🟢" if vals["macd"] > vals["macd_sig"] else "🔴" if vals["macd"] < vals["macd_sig"] else "⚪️"
    bias_rsi = _badge(vals["rsi"], pos="🟢", neg="🔴", mid="⚪️", thr_lo=45, thr_hi=55)
    bias_stoch = _badge(vals["stoch_k"], pos="🟢", neg="🔴", mid="⚪️", thr_lo=20, thr_hi=80)
    bias_adx = "💪" if vals["adx"] >= 20 else "😴"
    bias_vol = "🔥" if (not math.isnan(vals["vol_ratio"]) and vals["vol_ratio"] >= 1.5) else "•"

    # ---------- Markdown блок ----------
    md = []
    md.append(f"*{symbol}* *(TF={timeframe})* — **Indicators (12 preset)**")
    md.append("")
    md.append(f"- 💵 *Price*: `{_fmt(vals['price'], 2)}`")
    md.append(f"- 📈 *Trend*: {bias_trend} EMA50=`{_fmt(vals['ema50'],2)}`, EMA200=`{_fmt(vals['ema200'],2)}` | SMA7=`{_fmt(vals['sma7'],2)}`, SMA25=`{_fmt(vals['sma25'],2)}`")
    md.append(f"- 🔁 *MACD*: {bias_macd} MACD=`{_fmt(vals['macd'],4)}`, Signal=`{_fmt(vals['macd_sig'],4)}`, Hist=`{_fmt(vals['macd_hist'],4)}`")
    md.append(f"- 🎚 *RSI(14)*: {bias_rsi} `{_fmt(vals['rsi'],1)}` | *StochRSI* %K=`{_fmt(vals['stoch_k'],1)}` %D=`{_fmt(vals['stoch_d'],1)}`")
    md.append(f"- 💥 *ADX(14)*: {bias_adx} `{_fmt(vals['adx'],1)}` | *CCI(20)* `{_fmt(vals['cci'],1)}`")
    md.append(f"- 🌊 *ATR(14)*: `{_fmt(vals['atr'],3)}` ({_fmt(vals['atr_pct'],3)}%)")
    md.append(f"- 🎯 *Bollinger %B*: `{_fmt(vals['pct_b'],3)}`")
    md.append(f"- 📦 *OBV*: `{_fmt(vals['obv'],0)}` | *MFI(14)* `{_fmt(vals['mfi'],1)}`")
    md.append(f"- 📊 *Volume*: `{_fmt(vals['vol'],2)}` (x`{_fmt(vals['vol_ratio'],2)}` vs 20-bar avg) {bias_vol}")
    md.append(f"- 🧭 *Pivots*: P=`{_fmt(vals['pivot'],2)}` | R1=`{_fmt(vals['r1'],2)}` R2=`{_fmt(vals['r2'],2)}` R3=`{_fmt(vals['r3'],2)}` | S1=`{_fmt(vals['s1'],2)}` S2=`{_fmt(vals['s2'],2)}` S3=`{_fmt(vals['s3'],2)}`")
    md.append("")
    return "\n".join(md)
