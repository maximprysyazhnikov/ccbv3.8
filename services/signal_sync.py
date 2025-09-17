# services/signal_sync.py
from __future__ import annotations
import os, sqlite3, logging
from datetime import datetime, timezone

log = logging.getLogger("signal_sync")
DB_PATH = os.getenv("DB_PATH") or "storage/bot.db"

def _conn():
    c = sqlite3.connect(DB_PATH, timeout=30)
    c.row_factory = sqlite3.Row
    return c

def _table(c) -> str:
    row = c.execute("""
      SELECT name FROM sqlite_master 
      WHERE type='table' AND name IN ('trades','signals')
      ORDER BY CASE name WHEN 'trades' THEN 0 ELSE 1 END
      LIMIT 1;
    """).fetchone()
    return row["name"] if row else "signals"

def sync_signals_once() -> int:
    try:
        with _conn() as c:
            table = _table(c)
            cols = {r[1] for r in c.execute(f"PRAGMA table_info({table});")}
            tcol = "updated_at" if "updated_at" in cols else ("closed_at" if "closed_at" in cols else None)
            if not tcol:
                log.info("signal_sync: skip (no time column in %s)", table)
                return 0

            # приклад обережних апдейтів: reason_close з pnl, тільки якщо колонки існують
            if "reason_close" in cols and "pnl_usd" in cols:
                c.execute(f"""
                  UPDATE {table}
                  SET reason_close = CASE 
                      WHEN pnl_usd > 0 THEN 'tp'
                      WHEN pnl_usd < 0 THEN 'sl'
                      ELSE COALESCE(reason_close,'manual') END
                  WHERE UPPER(status) IN ('CLOSED','WIN','LOSS') AND (reason_close IS NULL OR reason_close='');
                """)

            updated = c.total_changes
            if updated:
                log.info("signal_sync: updated %s rows in %s", updated, table)
            return updated
    except sqlite3.OperationalError as e:
        log.warning("signal_sync sqlite error: %s", e); return 0
    except Exception as e:
        log.warning("signal_sync failed: %s", e); return 0
