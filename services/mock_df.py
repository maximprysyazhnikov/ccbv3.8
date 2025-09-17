# services/mock_df.py
from __future__ import annotations
import math
import random
from typing import Literal
import pandas as pd

Direction = Literal["LONG", "SHORT"]

def generate_trend_df(
    direction: Direction = "LONG",
    n: int = 300,
    base_price: float = 60000.0,
    trend_strength: float = 0.25,  # 0..1 (більше — крутіший тренд)
    noise_level: float = 0.004,    # відсоток випадкового шуму
    vol_base: float = 1_000.0,
    vol_boost_last: float = 2.0,   # множник об'єму наприкінці, щоб VOL_REL >= 1.2
    big_atr: float = 0.20,         # 20% діапазон на свічку для ADX-сурогату >= 18
) -> pd.DataFrame:
    """
    Генерує df з колонками: close, high, low, volume
    Налаштований так, щоб:
      - тренд відповідав напрямку (EMA50 > EMA200 для LONG і навпаки)
      - ATR/close ~ big_atr дає ADX-сурогат >= 18
      - BBW/STD/об'єми достатні, щоб пройти BBW_MIN/VOL_REL_MIN
      - остання ціна відхилена від VWAP (VWAP_DIST_MIN)
    """
    random.seed(42)
    step = trend_strength * base_price * 0.002  # крок тренду
    # тренд вгору/вниз
    drift = step if direction == "LONG" else -step

    closes = []
    price = base_price
    for i in range(n):
        # трендовий крок
        price += drift
        # шум (відносний)
        price *= (1.0 + random.uniform(-noise_level, noise_level))
        closes.append(price)

    close = pd.Series(closes, name="close")
    # створюємо широкий high/low для великого ATR (20% від ціни)
    hl_spread = close.abs() * big_atr
    high = close + hl_spread * (0.5 + random.random()*0.1)
    low  = close - hl_spread * (0.5 + random.random()*0.1)

    # об'єми: базові + підйом в останніх 30 свічок
    volume = pd.Series([vol_base * (0.8 + random.random()*0.4) for _ in range(n)], name="volume")
    volume.iloc[-30:] = volume.iloc[-30:] * vol_boost_last

    df = pd.DataFrame({"close": close, "high": high, "low": low, "volume": volume})
    # легкий «ривок» наприкінці, щоб збільшити VWAP_DIST і MACD/RSI
    bump = 0.01 * df["close"].iloc[-1]
    df.loc[df.index[-5]:, "close"] += (bump if direction == "LONG" else -bump)
    df.loc[df.index[-5]:, "high"]  += (bump if direction == "LONG" else -bump)
    df.loc[df.index[-5]:, "low"]   += (bump if direction == "LONG" else -bump)

    return df.reset_index(drop=True)
