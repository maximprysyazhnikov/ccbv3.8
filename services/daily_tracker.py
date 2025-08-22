# services/daily_tracker.py
from __future__ import annotations
import os, sqlite3, time
from dataclasses import dataclass
from typing import Optional, Tuple, List
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

DB_PATH = os.getenv("DB_PATH", "storage/app.db")
TZ = ZoneInfo(os.getenv("TZ_NAME", "Europe/Kyiv"))

# ─────────────── DB helpers ───────────────
def _conn() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn

def _fmt_money(x: float) -> str:
    sign = "➕" if x >= 0 else "➖"
    return f"{sign} ${abs(x):.2f}"

@dataclass
class Trade:
    id: int
    user_id: int
    symbol: str
    tf: str
    direction: str  # LONG/SHORT
    entry: float
    sl: float
    tp: float
    rr: float
    status: str     # WIN/LOSS/OPEN/...
    pnl_pct: Optional[float]

# ─────────────── core calc ───────────────
def _calc_pct(t: Trade) -> float:
    """PnL% для закритої угоди. Якщо pnl_pct є в БД — беремо його."""
    if t.pnl_pct is not None:
        return float(t.pnl_pct)
    if t.status == "WIN":
        if t.direction == "LONG":
            return (t.tp / t.entry - 1.0) * 100.0
        else:
            return (1.0 - t.tp / t.entry) * 100.0
    if t.status == "LOSS":
        if t.direction == "LONG":
            return (t.sl / t.entry - 1.0) * 100.0
        else:
            return (1.0 - t.sl / t.entry) * 100.0
    return 0.0

def _usd(pct: float, stake: float = 100.0) -> float:
    return round(stake * pct / 100.0, 2)

# ─────────────── public API ───────────────
def compute_daily_summary(
    user_id: int,
    day_ymd: Optional[Tuple[int, int, int]] = None,
    rr_min: Optional[float] = None,
) -> Tuple[dict, str]:
    """
    Повертає (metrics, markdown) для денного P&L користувача з фільтром RR≥rr_min.
    metrics: {'trades','wins','losses','winrate','sum_usd','avg_usd','avg_pct'}
    """
    # межі дня у локальному TZ
    if day_ymd:
        y, m, d = day_ymd
        t0 = int(time.mktime(time.strptime(f"{y:04d}-{m:02d}-{d:02d} 00:00:00", "%Y-%m-%d %H:%M:%S")))
    else:
        lt = time.localtime()
        t0 = int(time.mktime(time.strptime(time.strftime("%Y-%m-%d 00:00:00", lt), "%Y-%m-%d %H:%M:%S")))
    t1 = t0 + 86400 - 1

    with _conn() as conn:
        cur = conn.cursor()
        if rr_min is None:
            try:
                cur.execute("SELECT COALESCE(daily_rr,3.0) FROM user_settings WHERE user_id=?", (user_id,))
                row = cur.fetchone()
                rr_min = float(row[0] if row else 3.0)
            except sqlite3.OperationalError:
                rr_min = 3.0

        cur.execute(
            """
            SELECT id,user_id,symbol,tf,direction,entry,sl,tp,rr,status,pnl_pct
            FROM signals
            WHERE user_id=? AND status IN('WIN','LOSS')
              AND COALESCE(rr,0) >= ?
              AND COALESCE(ts_closed, ts_created) BETWEEN ? AND ?
            ORDER BY COALESCE(ts_closed, ts_created) ASC
            """,
            (user_id, rr_min, t0, t1),
        )
        rows = cur.fetchall()

    trades: List[Trade] = [
        Trade(
            id=int(r["id"]),
            user_id=int(r["user_id"]),
            symbol=str(r["symbol"]),
            tf=str(r["tf"]),
            direction=str(r["direction"]),
            entry=float(r["entry"]),
            sl=float(r["sl"]),
            tp=float(r["tp"]),
            rr=float(r["rr"]),
            status=str(r["status"]),
            pnl_pct=(None if r["pnl_pct"] is None else float(r["pnl_pct"])),
        )
        for r in rows
    ]

    wins = sum(1 for t in trades if t.status == "WIN")
    losses = sum(1 for t in trades if t.status == "LOSS")
    n = len(trades)
    winrate = round(100.0 * wins / n, 2) if n else 0.0

    total_usd = 0.0
    total_pct = 0.0
    lines = []

    for t in trades:
        pct = _calc_pct(t)
        usd = _usd(pct, 100.0)
        total_usd += usd
        total_pct += pct
        lines.append(f"{t.symbol} {t.tf:<4}  {pct:>6.2f}%   {usd:>8.2f}")

    avg_usd = round(total_usd / n, 2) if n else 0.0
    avg_pct = round(total_pct / n, 2) if n else 0.0

    day_str = datetime.fromtimestamp(t0, TZ).strftime("%Y-%m-%d")
    md_lines = [
        f"**📅 Daily P&L — {day_str} (RR≥{rr_min:g}, $100/угода)**",
        "",
        f"Угод: **{n}** | WIN: **{wins}** | LOSS: **{losses}** | Winrate: **{winrate:.2f}%**",
        f"Разом: **{_fmt_money(total_usd)}** | Середнє/угода: **{_fmt_money(avg_usd)}** (~{avg_pct:.2f}%)",
    ]
    if lines:
        md_lines += ["", "```", "Pair/TF        PnL%      PnL($)", "--------------------------------", *lines, "```"]
    md = "\n".join(md_lines)

    metrics = {
        "trades": n,
        "wins": wins,
        "losses": losses,
        "winrate": winrate,
        "sum_usd": round(total_usd, 2),
        "avg_usd": avg_usd,
        "avg_pct": avg_pct,
    }
    return metrics, md

# ─────────────── PTB jobs / test commands ───────────────
async def daily_tracker_job(context) -> None:
    """
    JobQueue callback: шле щоденний звіт усім користувачам, у кого daily_tracker=1.
    """
    bot = getattr(context, "bot", None) or getattr(getattr(context, "application", None), "bot", None)
    if bot is None and getattr(context, "job", None) and context.job.data:
        bot = context.job.data.get("bot")

    # беремо список користувачів з увімкненим трекером
    with _conn() as conn:
        cur = conn.cursor()
        try:
            cur.execute("SELECT user_id, COALESCE(daily_rr,3.0) as daily_rr FROM user_settings WHERE COALESCE(daily_tracker,0)=1")
            users = cur.fetchall()
        except sqlite3.OperationalError:
            users = []

    for r in users:
        uid = int(r["user_id"])
        rr_min = float(r["daily_rr"])
        try:
            _, md = compute_daily_summary(uid, rr_min=rr_min)
            if bot:
                await bot.send_message(chat_id=uid, text=md, parse_mode="Markdown")
        except Exception as e:
            if bot:
                await bot.send_message(chat_id=uid, text=f"⚠️ Daily tracker помилка: {e}")

# утилітна команда для миттєвого тесту з чату
async def daily_now(bot, chat_id: int) -> None:
    try:
        # day_ymd=None → сьогодні
        uid = chat_id  # один-до-одного для приватного чату
        _, md = compute_daily_summary(uid)
        await bot.send_message(chat_id=chat_id, text=md, parse_mode="Markdown")
    except Exception as e:
        await bot.send_message(chat_id=chat_id, text=f"⚠️ daily_now error: {e}")
