from __future__ import annotations
from telegram import Bot
from core_config import CFG

def notify(msg: str):
    Bot(CFG.tg_token).send_message(chat_id=CFG.tg_chat_id, text=msg)

def alert_overbought(symbol: str, rsi_value: float, threshold: float = 70.0):
    if rsi_value >= threshold:
        notify(f"🚨 {symbol}: RSI={rsi_value:.1f} (>{threshold}) — можливий перегрів.")
