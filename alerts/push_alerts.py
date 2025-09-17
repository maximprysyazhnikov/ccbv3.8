from __future__ import annotations

import os
import sqlite3
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from typing import Optional, List

from utils.settings import get_setting

log = logging.getLogger("alerts")

DB_PATH = os.getenv("DB_PATH", "storage/bot.db")

@dataclass
class AlertCfg:
    tz_name: str = "Europe/Kyiv"
    chat_id: str = ""
    max_consec_losses: int = 4
    drawdown_alert_r: float = 0.05   # інтерпретуємо як абсолют у R (наприклад 0.05R)
    wr_window: int = 20
    wr_min: float = 0.4              # 40%

def _cfg() -> AlertCfg:
    tz = get_setting("tz_name", "Europe/Kyiv") or "Europe/Kyiv"
    chat = get_setting("telegram_chat_id", "") or os.getenv("TELEGRAM_CHAT_ID", "")
    mcl = int(float(get_setting("max_consecutive_losses", "4") or 4))
    dd = float(get_setting("drawdown_alert_pct", "0.05") or 0.05)
    wrw = int(float(get_setting("wr_window", "20") or 20))
    wrmin = float(get_setting("wr_min", "0.4") or 0.4)
    return AlertCfg(tz_name=tz, chat_id=chat, max_consec_losses=mcl, drawdown_alert_r=dd,
                    wr_window=wrw, wr_min=wrmin)

def _now_tz(tz_name: str) -> datetime:
    return datetime.now(ZoneInfo(tz_name))

def _day_bounds_utc(now_tz: datetime) -> tuple[int, int]:
    start = now_tz.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    return int(start.astimezone(timezone.utc).timestamp()), int(end.astimezone(timezone.utc).timestamp())

def _week_bounds_utc(now_tz: datetime) -> tuple[int, int]:
    start = now_tz - timedelta(days=now_tz.weekday())  # Monday 00:00
    start = start.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=7)
    return int(start.astimezone(timezone.utc).timestamp()), int(end.astimezone(timezone.utc).timestamp())

def _fetch_rr_between(cur: sqlite3.Cursor, start_ts: int, end_ts: int) -> List[float]:
    rows = cur.execute(
        "SELECT COALESCE(rr,0.0) FROM trades WHERE UPPER(COALESCE(status,''))='CLOSED' "
        "AND closed_at>=? AND closed_at<?",
        (start_ts, end_ts),
    ).fetchall()
    return [float(r[0] or 0.0) for r in rows]

def _consecutive_losses(cur: sqlite3.Cursor) -> int:
    rows = cur.execute(
        "SELECT COALESCE(rr,0.0) FROM trades WHERE UPPER(COALESCE(status,''))='CLOSED' "
        "ORDER BY closed_at DESC LIMIT 200"
    ).fetchall()
    cnt = 0
    for (rr,) in rows:
        if (rr or 0.0) <= 0.0:
            cnt += 1
        else:
            break
    return cnt

def _wr_window(cur: sqlite3.Cursor, n: int) -> float:
    if n <= 0: return 1.0
    rows = cur.execute(
        "SELECT COALESCE(rr,0.0) FROM trades WHERE UPPER(COALESCE(status,''))='CLOSED' "
        "ORDER BY closed_at DESC LIMIT ?",
        (n,),
    ).fetchall()
    if not rows: return 1.0
    wins = sum(1 for (rr,) in rows if float(rr or 0.0) > 0.0)
    return wins / len(rows)

def _sum_r(vals: List[float]) -> float:
    return sum(float(x or 0.0) for x in vals)

def _send(bot, chat_id: str, text: str) -> None:
    if not chat_id:
        log.warning("[alerts] chat_id is empty, message: %s", text)
        return
    if bot is None:
        # якщо викликати з CLI / без бота — пишемо у лог
        log.info("[alerts] %s", text)
        return
    try:
        bot.send_message(chat_id=chat_id, text=text, disable_web_page_preview=True)
    except Exception as e:
        log.warning("[alerts] send fail: %s", e)

def run_alerts_once(bot=None) -> int:
    """
    Перевіряє:
      • N підряд лосів
      • Дроудаун дня / тижня (сума R за період)
      • Падіння WR% за останні X угод
    Надсилає алерти у TG. Повертає кількість тригерів.
    """
    cfg = _cfg()
    now = _now_tz(cfg.tz_name)
    day_s, day_e = _day_bounds_utc(now)
    week_s, week_e = _week_bounds_utc(now)

    fired = 0
    with sqlite3.connect(DB_PATH) as con:
        cur = con.cursor()

        # consecutive losses
        cl = _consecutive_losses(cur)
        if cl >= cfg.max_consec_losses:
            fired += 1
            _send(bot, cfg.chat_id, f"⚠️ ALERT: {cl} лосів підряд. Ліміт {cfg.max_consec_losses}.")

        # daily drawdown (в R)
        day_rr = _sum_r(_fetch_rr_between(cur, day_s, day_e))
        if day_rr <= -abs(cfg.drawdown_alert_r):
            fired += 1
            _send(bot, cfg.chat_id, f"📉 ALERT: Дроудаун за сьогодні {day_rr:.2f}R ≤ -{cfg.drawdown_alert_r}R.")

        # weekly drawdown (в R)
        week_rr = _sum_r(_fetch_rr_between(cur, week_s, week_e))
        if week_rr <= -abs(cfg.drawdown_alert_r):
            fired += 1
            _send(bot, cfg.chat_id, f"📉 ALERT: Дроудаун за тиждень {week_rr:.2f}R ≤ -{cfg.drawdown_alert_r}R.")

        # WR% last N trades
        wr = _wr_window(cur, cfg.wr_window)
        if wr < cfg.wr_min:
            fired += 1
            _send(
                bot, cfg.chat_id,
                f"❗ ALERT: WR за останні {cfg.wr_window} угод = {wr*100:.1f}% < {cfg.wr_min*100:.0f}%."
            )

    if fired:
        log.info("[alerts] fired=%d (day=%.2fR, week=%.2fR, wr=%.1f%%, consec=%d)",
                 fired, day_rr, week_rr, wr*100, cl)
    else:
        log.info("[alerts] no triggers")
    return fired
