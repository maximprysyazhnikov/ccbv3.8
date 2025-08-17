from __future__ import annotations
import math
from datetime import datetime
from typing import Optional, List, Dict
from zoneinfo import ZoneInfo
from telegram import Bot
from core_config import MONITORED_SYMBOLS, DEFAULT_TIMEFRAME, TZ_NAME, TELEGRAM_CHAT_ID
from market_data.binance_data import get_ohlcv
from signal_tools.ta_calc import get_ta_indicators

def _fmt(ts):
    try:
        return ts.tz_convert(ZoneInfo(TZ_NAME)).strftime("%Y-%m-%d %H:%M:%S %Z")
    except Exception:
        return str(ts)

def _score(last)->float:
    price=float(last.get("close",0) or 0)
    rsi=float(last.get("rsi",50) or 50)
    macd=float(last.get("macd",0) or 0)-float(last.get("macd_signal",0) or 0)
    sma7=float(last.get("sma_7",price) or price)
    sma25=float(last.get("sma_25",price) or price)
    atr=float(last.get("atr_14",0) or 0)
    atr_pct=(atr/price*100) if price else 0.0
    trend=1.0 if sma7>sma25 else -1.0 if sma7<sma25 else 0.0
    mom=max(-1,min(1,(rsi-50)/20))
    macd_s=max(-1,min(1,macd*5))
    vola=max(0,min(1,atr_pct/1.0))
    return 0.9*trend+0.7*macd_s+0.6*mom+0.3*vola

def _bias(last)->str:
    try:
        rsi=float(last.get("rsi")); macd_d=float(last.get("macd"))-float(last.get("macd_signal"))
        sma7=float(last.get("sma_7")); sma25=float(last.get("sma_25"))
    except Exception: return "NEUTRAL"
    if sma7>sma25 and macd_d>0 and rsi>=52: return "LONG"
    if sma7<sma25 and macd_d<0 and rsi<=48: return "SHORT"
    return "NEUTRAL"

async def run_local_top5(bot: Bot, chat_id: Optional[str]=None):
    chat_id = chat_id or TELEGRAM_CHAT_ID
    rows: List[Dict]=[]
    for s in [x for x in MONITORED_SYMBOLS if x][:12]:
        try:
            df=get_ohlcv(s, DEFAULT_TIMEFRAME, 150)
            if df.empty: continue
            inds=get_ta_indicators(df); last=inds.iloc[-1]
            rows.append({
                "symbol":s, "score":_score(last), "bias":_bias(last),
                "price": float(last.get("close",0)), "rsi": float(last.get("rsi", float("nan"))),
                "macd_d": float(last.get("macd",0))-float(last.get("macd_signal",0)),
                "atr_pct": (float(last.get("atr_14",0))/float(last.get("close",1))*100) if float(last.get("close",0)) else float("nan"),
                "ts": last.name
            })
        except Exception: 
            continue
    if not rows:
        await bot.send_message(chat_id=chat_id, text="⚠️ Локальний автоскрінер: немає даних."); return
    rows.sort(key=lambda r: abs(r["score"]), reverse=True)
    top=rows[:5]
    lines=["🏁 Локальний автоскрінер (топ‑5):\n"]
    for r in top:
        arrow="▲" if r["bias"]=="LONG" else "▼" if r["bias"]=="SHORT" else "•"
        atr_txt="-" if r["atr_pct"]!=r["atr_pct"] else f"{r['atr_pct']:.3f}%"
        lines.append(f"{arrow} {r['symbol']}: {r['bias']}  | P={r['price']:.4f}  | RSI={r['rsi']:.1f}  | MACDΔ={r['macd_d']:.4f}  | ATR%={atr_txt}  | {_fmt(r['ts'])}")
    await bot.send_message(chat_id=chat_id, text="\n".join(lines))
