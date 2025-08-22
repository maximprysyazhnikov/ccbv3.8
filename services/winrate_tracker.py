# services/winrate_tracker.py
from __future__ import annotations
import os, sqlite3, time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from telegram import Bot

DB_PATH = os.getenv("DB_PATH", "storage/app.db")
TZ = ZoneInfo(os.getenv("TZ_NAME", "Europe/Kyiv"))

def _q(sql, params=()):
    con = sqlite3.connect(DB_PATH)
    try:
        cur = con.execute(sql, params)
        return cur.fetchall()
    finally:
        con.close()

def _winrate(rows) -> tuple[int,int,float]:
    wins = sum(1 for r in rows if r[-2] == "WIN")
    losses = sum(1 for r in rows if r[-2] == "LOSS")
    total = wins + losses
    wr = (wins*100.0/total) if total else 0.0
    return wins, losses, wr

async def winrate_job(bot: Bot, days: int = 7) -> None:
    since = int((datetime.now(TZ) - timedelta(days=days)).timestamp())
    rows = _q("SELECT * FROM signals WHERE ts_created>=? AND status IN('WIN','LOSS')", (since,))
    if not rows:
        return
    wins, losses, wr = _winrate(rows)
    txt = f"📈 Winrate {days}d: {wr:.1f}% (WIN {wins} / LOSS {losses})"
    uids = [r[1] for r in rows]
    for uid in sorted(set(uids)):
        try:
            await bot.send_message(chat_id=uid, text=txt)
        except Exception:
            pass

async def winrate_now(bot: Bot, chat_id: int, days: int = 7) -> None:
    since = int((datetime.now(TZ) - timedelta(days=days)).timestamp())
    rows = _q("SELECT * FROM signals WHERE ts_created>=? AND status IN('WIN','LOSS')", (since,))
    if not rows:
        await bot.send_message(chat_id=chat_id, text=f"ℹ️ Немає даних для winrate за {days} дн.")
        return
    wins, losses, wr = _winrate(rows)
    await bot.send_message(chat_id=chat_id, text=f"📊 Winrate {days}d: {wr:.1f}% (WIN {wins} / LOSS {losses})")
