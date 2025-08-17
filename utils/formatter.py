from datetime import datetime
from typing import Iterable
def bullet_line(symbol, bias, price, rsi, macd_d, atr_pct, ts_txt):
    arrow = "▲" if bias=="LONG" else "▼" if bias=="SHORT" else "•"
    atr_txt = "-" if atr_pct is None else f"{atr_pct}%"
    return f"{arrow} {symbol}: {bias}  | P={price:.4f}  | RSI={rsi}  | MACDΔ={macd_d}  | ATR%={atr_txt}  | {ts_txt}"
