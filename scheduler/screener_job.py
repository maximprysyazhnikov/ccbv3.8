from __future__ import annotations
import math
from datetime import datetime
from zoneinfo import ZoneInfo

from core_config import TZ_NAME
from gpt_analyst.symbol_screener import get_top_symbols
from market_data.binance_data import get_ohlcv
from signal_tools.ta_calc import get_ta_indicators
from telegram_bot.sender import send_alert

def _bias(last) -> str:
    try:
        rsi = float(last.get("rsi"))
        macd_d = float(last.get("macd")) - float(last.get("macd_signal"))
        sma7 = float(last.get("sma_7"))
        sma25 = float(last.get("sma_25"))
    except Exception:
        return "NEUTRAL"
    if sma7 > sma25 and macd_d > 0 and rsi >= 52: return "LONG"
    if sma7 < sma25 and macd_d < 0 and rsi <= 48: return "SHORT"
    return "NEUTRAL"

def run_once():
    symbols = get_top_symbols(20)
    lines = ["🏁 Глобальний автоскрінер (топ‑20):\n"]
    for s in symbols:
        try:
            df = get_ohlcv(s, "1m", 150)
            if df.empty: 
                continue
            inds = get_ta_indicators(df)
            last = inds.iloc[-1]
            price = float(last.get("close", 0))
            rsi = float(last.get("rsi"))
            macd_d = float(last.get("macd")) - float(last.get("macd_signal"))
            atr = float(last.get("atr_14"))
            atr_pct = (atr/price*100) if price else float("nan")
            ts = last.name
            ts_txt = ts.tz_convert(ZoneInfo(TZ_NAME)).strftime("%Y-%m-%d %H:%M:%S %Z")
            bias = _bias(last)
            arrow = "▲" if bias=="LONG" else "▼" if bias=="SHORT" else "•"
            atr_txt = "-" if (atr_pct!=atr_pct) else f"{atr_pct:.3f}%"
            lines.append(f"{arrow} {s}: {bias}  | P={price:.4f}  | RSI={rsi:.1f}  | MACDΔ={macd_d:.4f}  | ATR%={atr_txt}  | {ts_txt}")
        except Exception:
            continue
    send_alert("\n".join(lines))
