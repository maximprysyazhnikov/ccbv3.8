from __future__ import annotations

import logging
from typing import Optional
from datetime import datetime, timezone

from utils.db import get_conn
from utils.settings import get_setting
from services.pnl import calc_pnl_usd  # ← Додаємо імпорт

__all__ = ["manage_open_positions"]

log = logging.getLogger("position_manager")


def _get_setting_float(key: str, default: float) -> float:
    try:
        val = get_setting(key, str(default))
        return float(val if val is not None else default)
    except Exception:
        return default


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
                return float(mod.get_price(sym))  # type: ignore[attr-defined]
        except Exception:
            continue
    return None


def _rr_eps() -> float:
    try:
        return float(get_setting("rr_eps", "1e-6") or 1e-6)
    except Exception:
        return 1e-6


def _rr_current(entry: float, sl: float, px: float, direction: str) -> float:
    r = abs(entry - sl)
    if r <= _rr_eps():
        return 0.0
    if (direction or "LONG").upper() == "LONG":
        return (px - entry) / r
    else:
        return (entry - px) / r


def _now_ts() -> int:
    return int(datetime.now(timezone.utc).timestamp())


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


def _update_signal_linked(conn, trade_id: int, reason: str, closed_at: int) -> None:
    """Оновлює пов'язані сигнали при закритті позиції."""
    cols = [r[1] for r in conn.execute("PRAGMA table_info(signals)").fetchall()]
    if "trade_id" not in cols:
        return
    conn.execute(
        "UPDATE signals SET reason_close=?, closed_at=?, status='CLOSED' WHERE trade_id=?",
        (reason, closed_at, trade_id),
    )


def _close_position_with_pnl(conn, tid: int, symbol: str, direction: str,
                             entry: float, sl: float, close_price: float,
                             reason: str, partial_pct: float = 1.0) -> None:
    """Закриває позицію з детальним розрахунком PnL."""
    size_usd = _get_trade_size_usd(conn, tid)
    fees_bps = _get_fees_bps()

    rr_realized, pnl_usd = calc_pnl_usd(
        entry=entry,
        sl=sl,
        close_price=close_price,
        direction=direction,
        size_usd=size_usd,
        fees_bps=fees_bps,
        partial_pct=partial_pct
    )

    # Старий RR для сумісності
    r = abs(entry - sl)
    if r > _rr_eps():
        if (direction or "LONG").upper() == "LONG":
            rr_old = (close_price - entry) / r
        else:
            rr_old = (entry - close_price) / r
    else:
        rr_old = 0.0

    ts = _now_ts()

    if partial_pct >= 1.0:
        # Повне закриття
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
            (ts, close_price, reason, rr_realized, pnl_usd, tid),
        )

        _update_signal_linked(conn, tid, reason, ts)
        log.info(
            "[pm] CLOSE FULL trade#%s %s rr=%.2f→%.2f pnl=$%.2f reason=%s",
            tid, symbol, rr_old, rr_realized, pnl_usd, reason
        )
    else:
        # Часткове закриття - оновлюємо тільки прапорець і додаємо PnL
        conn.execute(
            "UPDATE trades SET partial_50_done=1, pnl_usd=COALESCE(pnl_usd,0)+? WHERE id=?",
            (pnl_usd, tid)
        )
        log.info(
            "[pm] PARTIAL CLOSE %.0f%% trade#%s %s pnl=$%.2f (total pnl updated)",
            partial_pct * 100, tid, symbol, pnl_usd
        )


def _apply_move_be(conn, tid: int, old_sl: float, entry: float) -> None:
    if abs(old_sl - entry) <= 1e-12:
        conn.execute("UPDATE trades SET be_done=1 WHERE id=?", (tid,))
    else:
        conn.execute("UPDATE trades SET sl=?, be_done=1 WHERE id=?", (entry, tid,))


def _apply_trail(conn, tid: int, direction: str, old_sl: float, px: float, atr: Optional[float]) -> float:
    k = _get_setting_float("atr_sl_mult", 2.0)
    if atr and atr > 0:
        if (direction or "LONG").upper() == "LONG":
            new_sl = max(old_sl, px - k * atr)
        else:
            new_sl = min(old_sl, px + k * atr)
    else:
        new_sl = old_sl

    if abs(new_sl - old_sl) > 1e-12:
        conn.execute("UPDATE trades SET sl=? WHERE id=?", (new_sl, tid))
        log.info("[pm] TRAIL trade#%s sl: %.6f → %.6f", tid, old_sl, new_sl)
    return new_sl


def _ensure_schema() -> None:
    with get_conn() as conn:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(trades)").fetchall()]
        if "partial_50_done" not in cols:
            conn.execute("ALTER TABLE trades ADD COLUMN partial_50_done INTEGER NOT NULL DEFAULT 0")
        if "be_done" not in cols:
            conn.execute("ALTER TABLE trades ADD COLUMN be_done INTEGER NOT NULL DEFAULT 0")
        if "rr" not in cols:
            conn.execute("ALTER TABLE trades ADD COLUMN rr REAL")
        # ← Додаємо нові колонки для детального PnL
        if "close_price" not in cols:
            conn.execute("ALTER TABLE trades ADD COLUMN close_price REAL")
        if "close_reason" not in cols:
            conn.execute("ALTER TABLE trades ADD COLUMN close_reason TEXT")
        if "rr_realized" not in cols:
            conn.execute("ALTER TABLE trades ADD COLUMN rr_realized REAL")
        if "pnl_usd" not in cols:
            conn.execute("ALTER TABLE trades ADD COLUMN pnl_usd REAL DEFAULT 0.0")
        if "size_usd" not in cols:
            conn.execute("ALTER TABLE trades ADD COLUMN size_usd REAL DEFAULT 100.0")
        if "closed_at" not in cols:
            conn.execute("ALTER TABLE trades ADD COLUMN closed_at INTEGER")
        if "status" not in cols:
            conn.execute("ALTER TABLE trades ADD COLUMN status TEXT")
        conn.commit()


_ensure_schema()


def manage_open_positions() -> int:
    """
    Менеджмент позицій:
      - при RR ≥ MOVE_BE_AT_RR (1.0) → часткове закриття 50% (з PnL розрахунком) + SL→BE (be_done=1)
      - при RR ≥ 1.5 → м'який трейл (ATR/свінги)
    Повертає кількість оновлених позицій.
    """
    move_be_at = _get_setting_float("move_be_at_rr", 1.0)
    partial_enabled = str(get_setting("partial_tp_enabled", "true")).lower() == "true"
    partial_pct = _get_setting_float("partial_tp_pct", 0.5)  # 50% закриття

    updated = 0
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, symbol, direction, entry, sl, status, partial_50_done, be_done "
            "FROM trades WHERE (status IS NULL OR UPPER(status)='OPEN')"
        ).fetchall()

        cols_sg = [r[1] for r in conn.execute("PRAGMA table_info(signals)").fetchall()]
        has_trade_id = "trade_id" in cols_sg
        has_atr_entry = "atr_entry" in cols_sg

        def _get_atr_for_trade(tid: int) -> Optional[float]:
            if not (has_trade_id and has_atr_entry):
                return None
            row = conn.execute(
                "SELECT atr_entry FROM signals WHERE trade_id=? ORDER BY id DESC LIMIT 1",
                (tid,),
            ).fetchone()
            return float(row[0]) if row and row[0] is not None else None

        for (tid, symbol, direction, entry, sl, status, partial_done, be_done) in rows:
            try:
                px = _get_price(symbol)
                if px is None:
                    log.debug("[pm] skip %s: no price provider", symbol)
                    continue

                rr_cur = _rr_current(float(entry), float(sl), float(px), direction or "LONG")
                changed = False

                # A) partial + BE
                if rr_cur >= move_be_at:
                    if partial_enabled and not partial_done:
                        # ← Часткове закриття з детальним PnL
                        _close_position_with_pnl(
                            conn, tid, symbol, direction or "LONG",
                            float(entry), float(sl), float(px),
                            reason="partial_tp", partial_pct=partial_pct
                        )
                        changed = True

                    if not be_done:
                        _apply_move_be(conn, tid, float(sl), float(entry))
                        changed = True
                        log.info("[pm] BE move trade#%s %s rr=%.2f", tid, symbol, rr_cur)

                # B) трейл при ≥1.5R
                if rr_cur >= 1.5:
                    atr = _get_atr_for_trade(tid)
                    new_sl = _apply_trail(conn, tid, direction or "LONG", float(sl), float(px), atr)
                    if abs(new_sl - float(sl)) > 1e-12:
                        changed = True

                if changed:
                    updated += 1

            except Exception as e:
                log.warning("[pm] failed trade#%s %s: %s", tid, symbol, e)

        conn.commit()

    return updated

# ← Додаткова функція для мануального закриття з PnL
