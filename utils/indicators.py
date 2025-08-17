import numpy as np
import pandas as pd


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = np.where(delta > 0, delta, 0)
    loss = np.where(delta < 0, -delta, 0)
    avg_gain = pd.Series(gain).rolling(period).mean()
    avg_loss = pd.Series(loss).rolling(period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def stoch_rsi(series: pd.Series, period: int = 14, k: int = 14, d: int = 3) -> pd.DataFrame:
    rsi_series = rsi(series, period)
    min_rsi = rsi_series.rolling(k).min()
    max_rsi = rsi_series.rolling(k).max()
    stoch = (rsi_series - min_rsi) / (max_rsi - min_rsi) * 100
    k_line = stoch.rolling(d).mean()
    d_line = k_line.rolling(d).mean()
    return pd.DataFrame({"STOCHRSI_K": k_line, "STOCHRSI_D": d_line})


def macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    ema_fast = ema(series, fast)
    ema_slow = ema(series, slow)
    macd_line = ema_fast - ema_slow
    signal_line = ema(macd_line, signal)
    return pd.DataFrame({"MACD": macd_line, "MACD_SIGNAL": signal_line})


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high_low = df["high"] - df["low"]
    high_close = (df["high"] - df["close"].shift()).abs()
    low_close = (df["low"] - df["close"].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def bollinger_bands(series: pd.Series, period: int = 20, std_factor: float = 2.0) -> pd.DataFrame:
    sma = series.rolling(period).mean()
    std = series.rolling(period).std()
    upper = sma + std_factor * std
    lower = sma - std_factor * std
    pct_b = (series - lower) / (upper - lower)
    return pd.DataFrame({"BB_UPPER": upper, "BB_LOWER": lower, "PCTB": pct_b})


def obv(df: pd.DataFrame) -> pd.Series:
    direction = np.sign(df["close"].diff()).fillna(0)
    return (direction * df["volume"]).cumsum()


def mfi(df: pd.DataFrame, period: int = 14) -> pd.Series:
    tp = (df["high"] + df["low"] + df["close"]) / 3
    mf = tp * df["volume"]
    pos_mf = np.where(tp > tp.shift(1), mf, 0)
    neg_mf = np.where(tp < tp.shift(1), mf, 0)
    pos_mf_sum = pd.Series(pos_mf).rolling(period).sum()
    neg_mf_sum = pd.Series(neg_mf).rolling(period).sum()
    mfr = pos_mf_sum / neg_mf_sum
    return 100 - (100 / (1 + mfr))


def adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    plus_dm = df["high"].diff()
    minus_dm = df["low"].diff().abs()
    plus_dm = np.where((plus_dm > minus_dm) & (plus_dm > 0), plus_dm, 0.0)
    minus_dm = np.where((minus_dm > plus_dm) & (df["low"].diff() < 0), minus_dm, 0.0)

    tr = pd.concat([
        (df["high"] - df["low"]),
        (df["high"] - df["close"].shift()).abs(),
        (df["low"] - df["close"].shift()).abs()
    ], axis=1).max(axis=1)

    atr_series = tr.rolling(period).mean()

    plus_di = 100 * (pd.Series(plus_dm).rolling(period).sum() / atr_series)
    minus_di = 100 * (pd.Series(minus_dm).rolling(period).sum() / atr_series)
    dx = (abs(plus_di - minus_di) / (plus_di + minus_di)) * 100
    return dx.rolling(period).mean()


def cci(df: pd.DataFrame, period: int = 20) -> pd.Series:
    tp = (df["high"] + df["low"] + df["close"]) / 3
    sma = tp.rolling(period).mean()
    mad = (tp - sma).abs().rolling(period).mean()
    return (tp - sma) / (0.015 * mad)


def fibonacci_pivots(df: pd.DataFrame) -> pd.DataFrame:
    last = df.iloc[-2]  # попередня свічка
    high, low, close = last["high"], last["low"], last["close"]
    pivot = (high + low + close) / 3
    r1 = pivot + (high - low) * 0.382
    r2 = pivot + (high - low) * 0.618
    r3 = pivot + (high - low) * 1.0
    s1 = pivot - (high - low) * 0.382
    s2 = pivot - (high - low) * 0.618
    s3 = pivot - (high - low) * 1.0
    return pd.DataFrame([{
        "FIB_PIVOT": pivot, "FIB_R1": r1, "FIB_R2": r2, "FIB_R3": r3,
        "FIB_S1": s1, "FIB_S2": s2, "FIB_S3": s3
    }], index=[df.index[-1]])


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df["EMA50"] = ema(df["close"], 50)
    df["EMA200"] = ema(df["close"], 200)

    macd_df = macd(df["close"])
    df["MACD"] = macd_df["MACD"]
    df["MACD_SIGNAL"] = macd_df["MACD_SIGNAL"]

    df["RSI"] = rsi(df["close"])
    stoch_df = stoch_rsi(df["close"])
    df["STOCHRSI_K"] = stoch_df["STOCHRSI_K"]
    df["STOCHRSI_D"] = stoch_df["STOCHRSI_D"]

    df["ATR"] = atr(df)
    bb_df = bollinger_bands(df["close"])
    df["BB_UPPER"] = bb_df["BB_UPPER"]
    df["BB_LOWER"] = bb_df["BB_LOWER"]
    df["PCTB"] = bb_df["PCTB"]

    df["OBV"] = obv(df)
    df["MFI"] = mfi(df)
    df["ADX"] = adx(df)
    df["CCI"] = cci(df)

    pivots_df = fibonacci_pivots(df)
    for col in pivots_df.columns:
        df[col] = pivots_df[col]

    return df
