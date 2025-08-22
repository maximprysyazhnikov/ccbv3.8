# services/autopost.py
from __future__ import annotations
import os, re, sqlite3, time, logging, uuid, math   # ← додали math
from typing import List, Dict, Any, Optional

from core_config import CFG
from services.analyzer_core import generate_trade_plan
from services.signals_repo import insert_open_signal
from market_data.candles import snapshot_ts

log = logging.getLogger("autopost")

_DB_PATH = (
    os.getenv("DB_PATH")
    or os.getenv("SQLITE_PATH")
    or os.getenv("DATABASE_PATH")
    or "storage/bot.db"
)

def _conn():
    os.makedirs(os.path.dirname(_DB_PATH) or ".", exist_ok=True)
    c = sqlite3.connect(_DB_PATH, timeout=30); c.row_factory = sqlite3.Row
    return c

def _get_users_with_autopost():
    with _conn() as c:
        cur = c.cursor()
        cur.execute("""
            SELECT user_id, timeframe, autopost, autopost_tf, autopost_rr,
                   rr_threshold, model_key, locale
            FROM user_settings
            WHERE COALESCE(autopost,0)=1
        """)
        return cur.fetchall()

def _fmt_or_dash(v):
    try: return f"{float(v):.4f}"
    except: return "-"

def _compute_rr_num(direction: str, entry, stop, tp) -> Optional[float]:
    try:
        e = float(entry); s = float(stop); t = float(tp)
        if any(math.isnan(x) or math.isinf(x) for x in (e, s, t)): return None
        direction = (direction or "").upper()
        if direction == "LONG":
            risk = e - s; reward = t - e
        elif direction == "SHORT":
            risk = s - e; reward = e - t
        else:
            return None
        if risk <= 0 or reward <= 0: return None
        return float(reward / risk)
    except Exception:
        return None

def run_autopost_once(app=None) -> List[Dict[str, Any]]:
    msgs: List[Dict[str, Any]] = []
    users = _get_users_with_autopost()
    if not users:
        log.info("autopost: no users with autopost=1")
        return msgs

    symbols = [s.strip().upper() for s in CFG.get("symbols", []) if s.strip()]
    if not symbols:
        log.warning("autopost: CFG['symbols'] is empty")
        return msgs

    # єдиний snapshot для всього запуску
    snap = snapshot_ts()
    batch_id = uuid.uuid4().hex

    for u in users:
        uid = int(u["user_id"])
        tf = (u["autopost_tf"] or u["timeframe"] or CFG.get("analyze_timeframe","15m")).strip()
        rr_min = float(u["autopost_rr"] or u["rr_threshold"] or CFG.get("rr_threshold", 1.5))
        locale = (u["locale"] or CFG.get("default_locale","uk")).strip().lower()
        model_key = (u["model_key"] or "auto").strip()
        size_usd = float(CFG.get("kpi_size_usd", 100.0))

        for sym in symbols:
            try:
                plan, indi_md = generate_trade_plan(sym, tf, user_model_key=model_key, locale=locale)

                # 1) RR: беремо з плану або рахуємо з entry/stop/tp
                rr = plan.get("rr")
                try:
                    rr = float(rr) if rr is not None else None
                    if rr is not None and (math.isnan(rr) or math.isinf(rr) or rr <= 0):
                        rr = None
                except Exception:
                    rr = None
                if rr is None:
                    rr = _compute_rr_num(plan.get("direction"), plan.get("entry"), plan.get("stop"), plan.get("tp"))

                # 2) якщо немає валідного RR або він нижче порога — скіпаємо з поясненням
                if rr is None:
                    log.info("autopost skip %s [%s]: RR is None (dir=%s entry=%s stop=%s tp=%s)",
                             sym, tf, plan.get("direction"), plan.get("entry"), plan.get("stop"), plan.get("tp"))
                    continue
                if rr < rr_min:
                    log.info("autopost skip %s [%s]: rr=%.2f < rr_min=%.2f", sym, tf, rr, rr_min)
                    continue

                # 3) зберігаємо OPEN
                insert_open_signal(
                    user_id=uid, source="autopost", symbol=sym, timeframe=tf,  # ← OK: signals_repo мапить timeframe→tf
                    direction=plan.get("direction","NEUTRAL"),
                    entry=plan.get("entry"), stop=plan.get("stop"), tp=plan.get("tp"),
                    rr=rr, size_usd=size_usd, analysis_id=batch_id, snapshot_ts=snap
                )

                # 4) повідомлення
                text = (
                    f"🤖 Autopost plan {sym} [{tf}]\n"
                    f"Dir: {plan.get('direction') or '-'} | RR≈{_fmt_or_dash(rr)}\n"
                    f"Entry: {_fmt_or_dash(plan.get('entry'))} | "
                    f"SL: {_fmt_or_dash(plan.get('stop'))} | "
                    f"TP: {_fmt_or_dash(plan.get('tp'))}\n"
                    f"Snapshot: {snap}"
                )
                msgs.append({"chat_id": uid, "text": text, "parse_mode": None, "disable_web_page_preview": True})

                if indi_md:
                    msgs.append({"chat_id": uid, "text": "📈 Indicators:\n" + indi_md, "parse_mode": "Markdown",
                                 "disable_web_page_preview": True})

            except Exception as e:
                log.warning("autopost %s %s failed: %s", sym, tf, e)

    log.info("autopost: prepared %d messages", len(msgs))
    return msgs
