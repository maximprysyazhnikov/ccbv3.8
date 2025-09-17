from __future__ import annotations
import logging
from datetime import datetime, timezone
from typing import Optional

from utils.db import get_conn
from utils.settings import get_setting
from services.pnl import calc_pnl_usd  # ← Додаємо імпорт

log = logging.getLogger("signal_closer")


def _now_ts() -> int:
    return int(datetime.now(timezone.utc).timestamp())


def _rr_eps() -> float:
    try:
        return float(get_setting("rr_eps", "1e-6") or 1e-6)
    except Exception:
        return 1e-6


# ───────────────────────── schema guard ─────────────────────────
def _ensure_schema() -> None:
    """Ідемпотентно додаємо потрібні колонки/індекси, якщо їх ще нема."""
    with get_conn() as conn:
        # trades
        cols_tr = [r[1] for r in conn.execute("PRAGMA table_info(trades)").fetchall()]
        if "partial_50_done" not in cols_tr:
            conn.execute("ALTER TABLE trades ADD COLUMN partial_50_done INTEGER NOT NULL DEFAULT 0")
        if "be_done" not in cols_tr:
            conn.execute("ALTER TABLE trades ADD COLUMN be_done INTEGER NOT NULL DEFAULT 0")
        if "closed_at" not in cols_tr:
            conn.execute("ALTER TABLE trades ADD COLUMN closed_at INTEGER")
        if "status" not in cols_tr:
            conn.execute("ALTER TABLE trades ADD COLUMN status TEXT")
        if "pnl" not in cols_tr:
            conn.execute("ALTER TABLE trades ADD COLUMN pnl REAL DEFAULT 0.0")
        if "rr" not in cols_tr:
            conn.execute("ALTER TABLE trades ADD COLUMN rr REAL")
        # ← Додаємо нові колонки для детального PnL
        if "close_price" not in cols_tr:
            conn.execute("ALTER TABLE trades ADD COLUMN close_price REAL")
        if "close_reason" not in cols_tr:
            conn.execute("ALTER TABLE trades ADD COLUMN close_reason TEXT")
        if "rr_realized" not in cols_tr:
            conn.execute("ALTER TABLE trades ADD COLUMN rr_realized REAL")
        if "pnl_usd" not in cols_tr:
            conn.execute("ALTER TABLE trades ADD COLUMN pnl_usd REAL DEFAULT 0.0")
        if "size_usd" not in cols_tr:
            conn.execute("ALTER TABLE trades ADD COLUMN size_usd REAL DEFAULT 100.0")

        # signals
        try:
            cols_sg = [r[1] for r in conn.execute("PRAGMA table_info(signals)").fetchall()]
            if "reason_close" not in cols_sg:
                conn.execute("ALTER TABLE signals ADD COLUMN reason_close TEXT")
            if "closed_at" not in cols_sg:
                conn.execute("ALTER TABLE signals ADD COLUMN closed_at INTEGER")
            if "status" not in cols_sg:
                conn.execute("ALTER TABLE signals ADD COLUMN status TEXT")
            if "decision" not in cols_sg:
                conn.execute("ALTER TABLE signals ADD COLUMN decision TEXT")
            # індекси
            if not conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='index' AND name='ix_signals_closed_at'").fetchone():
                conn.execute("CREATE INDEX IF NOT EXISTS ix_signals_closed_at ON signals(closed_at)")
            if not conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='index' AND name='ix_signals_status'").fetchone():
                conn.execute("CREATE INDEX IF NOT EXISTS ix_signals_status ON signals(status)")
        except Exception as e:
            log.warning("[schema] signals patch warn: %s", e)

        conn.commit()


_ensure_schema()


# ───────────────────────── helpers ─────────────────────────
def _rr_from_exit(entry: float, sl: float, exit_price: float, direction: str) -> float:
    r = abs(entry - sl)
    if r <= _rr_eps():
        return 0.0
    if (direction or "LONG").upper() == "LONG":
        return (exit_price - entry) / r
    else:
        return (entry - exit_price) / r


def _update_signal_linked(conn, trade_id: int, reason: str, closed_at: int) -> None:
    cols = [r[1] for r in conn.execute("PRAGMA table_info(signals)").fetchall()]
    if "trade_id" not in cols:
        return
    conn.execute(
        "UPDATE signals SET reason_close=?, closed_at=?, status='CLOSED' WHERE trade_id=?",
        (reason, closed_at, trade_id),
    )


def _has_neutral_signal(conn, trade_id: int) -> bool:
    cols = [r[1] for r in conn.execute("PRAGMA table_info(signals)").fetchall()]
    if "trade_id" not in cols:
        return False
    if "decision" in cols:
        row = conn.execute(
            "SELECT 1 FROM signals WHERE trade_id=? AND UPPER(COALESCE(decision,''))='NEUTRAL' "
            "ORDER BY id DESC LIMIT 1",
            (trade_id,),
        ).fetchone()
        if row:
            return True
    if "status" in cols:
        row = conn.execute(
            "SELECT 1 FROM signals WHERE trade_id=? AND UPPER(COALESCE(status,''))='NEUTRAL' "
            "ORDER BY id DESC LIMIT 1",
            (trade_id,),
        ).fetchone()
        if row:
            return True
    return False


def _get_price(sym: str) -> Optional[float]:
    for path in (
            "services.market",
            "services.price_provider",
            "services.binance_price",
            "services.binance",
            "services.prices",
    ):
        try:
            mod = __import__(path, fromlist=["get_price"])
            if hasattr(mod, "get_price"):
                return float(mod.get_price(sym))  # type: ignore
        except Exception:
            continue
    return None


def _get_trade_size_usd(conn, trade_id: int) -> float:
    """Отримує розмір позиції з БД або використовує дефолт."""
    try:
        row = conn.execute("SELECT size_usd FROM trades WHERE id=?", (trade_id,)).fetchone()
        if row and row[0] is not None:
            return float(row[0])
    except Exception:
        pass
    return float(get_setting("default_position_size_usd", "100.0") or 100.0)


def _get_fees_bps() -> int:
    """Отримує комісію в базисних пунктах з налаштувань."""
    try:
        return int(get_setting("trading_fees_bps", "10") or 10)
    except Exception:
        return 10


# ───────────────────────── core actions ─────────────────────────
def _close_trade_row(conn, tr: tuple, reason: str, exit_price: Optional[float]) -> None:
    tid, symbol, direction, entry, sl, status = tr
    entry = float(entry or 0.0)
    sl = float(sl or 0.0)
    exit_px = entry if exit_price is None else float(exit_price)

    # ← Старий розрахунок RR (залишаємо для сумісності)
    rr = _rr_from_exit(entry, sl, exit_px, direction or "LONG")
    pnl = rr  # у R

    # ← НОВИЙ розрахунок з детальним PnL
    size_usd = _get_trade_size_usd(conn, tid)
    fees_bps = _get_fees_bps()

    rr_realized, pnl_usd = calc_pnl_usd(
        entry=entry,
        sl=sl,
        close_price=exit_px,
        direction=direction or "LONG",
        size_usd=size_usd,
        fees_bps=fees_bps,
        partial_pct=1.0  # повне закриття
    )

    ts = _now_ts()

    # ← Оновлюємо з новими полями
    conn.execute(
        """
        UPDATE trades
           SET status='CLOSED',
               closed_at=?,
               close_price=?,
               close_reason=?,
               rr_realized=?,
               pnl_usd=?
         WHERE id=?
        """,
        (ts, exit_px, reason, rr_realized, pnl_usd, tid),
    )

    _update_signal_linked(conn, tid, reason, ts)
    log.info(
        "[neutral] CLOSE trade#%s %s rr=%.2f→%.2f pnl=$%.2f (exit=%.6f) reason=%s",
        tid, symbol, rr, rr_realized, pnl_usd, exit_px, reason
    )


def _trail_to_be(conn, tr: tuple) -> None:
    tid, symbol, direction, entry, sl, status, be_done = tr
    entry = float(entry or 0.0)
    sl = float(sl or 0.0)
    if be_done:
        return
    if abs(sl - entry) <= 1e-12:
        conn.execute("UPDATE trades SET be_done=1 WHERE id=?", (tid,))
        return
    conn.execute("UPDATE trades SET sl=?, be_done=1 WHERE id=?", (entry, tid))
    log.info("[neutral] TRAIL→BE trade#%s %s sl: %.6f → %.6f", tid, symbol, sl, entry)


# ───────────────────────── public API ─────────────────────────
def check_and_close_neutral() -> int:
    """
    Обробляє ТІЛЬКИ ті трейди, для яких Є NEUTRAL-сигнал у таблиці signals.
      - CLOSE: закриття (reason_close='neutral', closed_at, pnl, rr).
      - TRAIL: SL → BE (be_done=1).
      - IGNORE: нічого не робимо.
    """
    mode = (get_setting("neutral_mode", "TRAIL") or "TRAIL").strip().upper()
    if mode not in {"CLOSE", "TRAIL"}:
        log.debug("[neutral] mode=%s → nothing to do", mode)
        return 0

    updated = 0
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, symbol, direction, entry, sl, status, be_done FROM trades "
            "WHERE (status IS NULL OR UPPER(status)='OPEN')"
        ).fetchall()
        if not rows:
            return 0

        for tr in rows:
            tid, symbol, direction, entry, sl, status, be_done = tr
            try:
                if not _has_neutral_signal(conn, tid):
                    continue

                if mode == "CLOSE":
                    px = _get_price(symbol)
                    _close_trade_row(conn, (tid, symbol, direction, entry, sl, status), "neutral", px)
                    updated += 1
                elif mode == "TRAIL":
                    _trail_to_be(conn, tr)
                    updated += 1
            except Exception as e:
                log.warning("[neutral] action failed trade#%s %s: %s", tid, symbol, e)

        conn.commit()

    return updated


def close_signals_once() -> int:
    return check_and_close_neutral()
