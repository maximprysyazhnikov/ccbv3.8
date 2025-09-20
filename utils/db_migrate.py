# utils/db_migrate.py
from __future__ import annotations
import logging
import os
import sqlite3
from typing import Dict, Tuple, Any

from utils.db import get_conn

log = logging.getLogger("migrate")


# ──────────────────────────────────────────────
# helpers
# ──────────────────────────────────────────────
def _table_columns(conn: sqlite3.Connection, table: str) -> Dict[str, Tuple[str, int, Any]]:
    """
    Повертає {col_name: (col_type, notnull, dflt_value)}.
    """
    cols: Dict[str, Tuple[str, int, Any]] = {}
    for cid, name, ctype, notnull, dflt_value, pk in conn.execute(f"PRAGMA table_info({table})"):
        cols[name] = (ctype or "", int(notnull or 0), dflt_value)
    return cols


def _has_table(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return bool(row)


def _ensure_table(conn: sqlite3.Connection, table_sql: str) -> None:
    conn.execute(table_sql)


def _ensure_column(conn: sqlite3.Connection, table: str, col_name: str, decl: str) -> None:
    """
    Додає колонку, якщо її немає.
    УВАГА: SQLite ALTER TABLE ADD COLUMN не підтримує NOT NULL без дефолта,
    тому в decl не ставимо NOT NULL без DEFAULT.
    """
    cols = _table_columns(conn, table)
    if col_name not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {col_name} {decl}")


def _ensure_index(conn: sqlite3.Connection, name: str, sql: str) -> None:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='index' AND name=?",
        (name,),
    ).fetchone()
    if not row:
        conn.execute(sql)


def _upsert_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    row = conn.execute("SELECT 1 FROM settings WHERE key=?", (key,)).fetchone()
    if row:
        return
    conn.execute("INSERT INTO settings(key, value) VALUES(?, ?)", (key, value))


# ──────────────────────────────────────────────
# schema ensure (create-if-missing + add-missing-columns)
# ──────────────────────────────────────────────
def _ensure_signals(conn: sqlite3.Connection) -> None:
    if not _has_table(conn, "signals"):
        _ensure_table(conn, """
        CREATE TABLE IF NOT EXISTS signals(
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id       INTEGER DEFAULT 0,
            symbol        TEXT NOT NULL,
            timeframe     TEXT NOT NULL,
            direction     TEXT,
            entry         REAL,
            sl            REAL,
            tp            REAL,
            rr            REAL,
            source        TEXT,
            status        TEXT,
            opened_at     TEXT,
            closed_at     TEXT,
            pnl_usd       REAL,
            rr_real       REAL,
            tf            TEXT,
            analysis_id   TEXT,
            snapshot_ts   INTEGER,
            size_usd      REAL,
            ts_created    INTEGER,
            ts_closed     INTEGER,
            pnl_pct       REAL,
            details       TEXT,
            reason_close  TEXT,
            trend_ok      INTEGER,
            atr_entry     REAL,
            ema50         REAL,
            ema200        REAL,
            rr_target     REAL,
            entry_sl_dist REAL,
            trade_id      INTEGER,
            decision      TEXT,
            created_at    TEXT,
            reject_reason TEXT
        )""")

    desired: Dict[str, str] = {
        "user_id": "INTEGER",
        "symbol": "TEXT",
        "timeframe": "TEXT",
        "direction": "TEXT",
        "entry": "REAL",
        "sl": "REAL",
        "tp": "REAL",
        "rr": "REAL",
        "source": "TEXT",
        "status": "TEXT",
        "opened_at": "TEXT",
        "closed_at": "TEXT",
        "pnl_usd": "REAL",
        "rr_real": "REAL",
        "tf": "TEXT",
        "analysis_id": "TEXT",
        "snapshot_ts": "INTEGER",
        "size_usd": "REAL",
        "ts_created": "INTEGER",
        "ts_closed": "INTEGER",
        "pnl_pct": "REAL",
        "details": "TEXT",
        "reason_close": "TEXT",
        "trend_ok": "INTEGER",
        "atr_entry": "REAL",
        "ema50": "REAL",
        "ema200": "REAL",
        "rr_target": "REAL",
        "entry_sl_dist": "REAL",
        "trade_id": "INTEGER",
        "decision": "TEXT",
        "created_at": "TEXT",
        "reject_reason": "TEXT",
    }
    for col, decl in desired.items():
        _ensure_column(conn, "signals", col, decl)

    _ensure_index(conn, "ix_signals_closed_at",
                  "CREATE INDEX IF NOT EXISTS ix_signals_closed_at ON signals(closed_at)")
    _ensure_index(conn, "ix_signals_status",
                  "CREATE INDEX IF NOT EXISTS ix_signals_status ON signals(status)")


def _ensure_trades(conn: sqlite3.Connection) -> None:
    if not _has_table(conn, "trades"):
        _ensure_table(conn, """
        CREATE TABLE IF NOT EXISTS trades(
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            signal_id       INTEGER,
            symbol          TEXT NOT NULL,
            timeframe       TEXT NOT NULL,
            direction       TEXT,
            entry           REAL,
            sl              REAL,
            tp              REAL,
            opened_at       TEXT,
            closed_at       TEXT,
            close_reason    TEXT,
            status          TEXT,
            size_usd        REAL,
            fees_bps        REAL,
            rr_planned      REAL,
            pnl             REAL,
            rr              REAL,
            close_price     REAL,
            reason_close    TEXT,
            trend_ok        INTEGER,
            atr_entry       REAL,
            ema50           REAL,
            ema200          REAL,
            rr_target       REAL,
            entry_sl_dist   REAL,
            partial_50_done INTEGER,
            be_done         INTEGER,
            avg_entry       REAL,
            filled_buckets  INTEGER,
            target_rrs_json TEXT,
            pnl_usd         REAL,
            rr_realized     REAL,
            trail_mode      TEXT
        )""")

    desired: Dict[str, str] = {
        "signal_id": "INTEGER",
        "symbol": "TEXT",
        "timeframe": "TEXT",
        "direction": "TEXT",
        "entry": "REAL",
        "sl": "REAL",
        "tp": "REAL",
        "opened_at": "TEXT",
        "closed_at": "TEXT",
        "close_reason": "TEXT",
        "status": "TEXT",
        "size_usd": "REAL",
        "fees_bps": "REAL",
        "rr_planned": "REAL",
        "pnl": "REAL",
        "rr": "REAL",
        "close_price": "REAL",
        "reason_close": "TEXT",
        "trend_ok": "INTEGER",
        "atr_entry": "REAL",
        "ema50": "REAL",
        "ema200": "REAL",
        "rr_target": "REAL",
        "entry_sl_dist": "REAL",
        "partial_50_done": "INTEGER",
        "be_done": "INTEGER",
        "avg_entry": "REAL",
        "filled_buckets": "INTEGER",
        "target_rrs_json": "TEXT",
        "pnl_usd": "REAL",
        "rr_realized": "REAL",
        "trail_mode": "TEXT",
    }
    for col, decl in desired.items():
        _ensure_column(conn, "trades", col, decl)

    _ensure_index(conn, "ix_trades_closed_at",
                  "CREATE INDEX IF NOT EXISTS ix_trades_closed_at ON trades(closed_at)")


def _ensure_user_settings(conn: sqlite3.Connection) -> None:
    """
    Історично `user_settings` була KV-таблицею (user_id, key, value).
    Для сумісності з кодом, який читає колонками (autopost, autopost_rr, rr_threshold, neutral_mode),
    додаємо ці колонки напряму до цієї ж таблиці. Це безпечно: KV-схема лишається працездатною.
    """
    if not _has_table(conn, "user_settings"):
        _ensure_table(conn, """
        CREATE TABLE IF NOT EXISTS user_settings(
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id  INTEGER NOT NULL,
            key      TEXT NOT NULL,
            value    TEXT,
            UNIQUE(user_id, key)
        )""")

    # ── колонки, які очікують панелі/хендлери
    _ensure_column(conn, "user_settings", "autopost",      "INTEGER DEFAULT 1")
    _ensure_column(conn, "user_settings", "autopost_rr",   "REAL DEFAULT 1.5")
    _ensure_column(conn, "user_settings", "rr_threshold",  "REAL DEFAULT 1.5")
    _ensure_column(conn, "user_settings", "neutral_mode",  "TEXT DEFAULT 'TRAIL'")

    # індекси для швидких вибірок по user_id
    _ensure_index(conn, "ix_user_settings_user_id",
                  "CREATE INDEX IF NOT EXISTS ix_user_settings_user_id ON user_settings(user_id)")


def _ensure_settings(conn: sqlite3.Connection) -> None:
    if not _has_table(conn, "settings"):
        _ensure_table(conn, """
        CREATE TABLE IF NOT EXISTS settings(
            key    TEXT PRIMARY KEY,
            value  TEXT
        )""")

    # дефолти (ключі з чек-листа)
    defaults = {
        "tz_name": "Europe/Kyiv",
        "kpi_days": "7",
        "kpi_rr_bucket": "2",
        "neutral_mode": "TRAIL",           # CLOSE | TRAIL | IGNORE
        "min_entry_rr": "1.5",
        "risk_per_trade": "0.0075",
        "atr_sl_mult": "2.0",
        "partial_tp_enabled": "true",
        "partial_tp_pct": "0.5",
        "move_be_at_rr": "1.0",
        "indicator_gate_enabled": "false",
        "indicator_min_pass": "8",
        "atr_min": "0.004",
        "rsi_long_min": "50",
        "rsi_short_max": "50",
        "adx_min": "18",
        "bbw_min": "0.015",
        "vol_rel_min": "1.2",
        "vwap_dist_min": "0.0015",
        "signal_sync_enabled": "false",
        "rr_eps": "1e-6",
        "dedup_window_sec": "90",
        "autopost_user_id": "default",
    }
    for k, v in defaults.items():
        _upsert_setting(conn, k, v)


def _ensure_autopost_log(conn: sqlite3.Connection) -> None:
    if not _has_table(conn, "autopost_log"):
        _ensure_table(conn, """
        CREATE TABLE IF NOT EXISTS autopost_log(
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id   INTEGER DEFAULT 0,
            symbol    TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            rr        REAL,
            ts_sent   INTEGER,
            ts        INTEGER
        )""")

    desired: Dict[str, str] = {
        "user_id": "INTEGER",
        "symbol": "TEXT",
        "timeframe": "TEXT",
        "rr": "REAL",
        "ts_sent": "INTEGER",
        "ts": "INTEGER",
    }
    for col, decl in desired.items():
        _ensure_column(conn, "autopost_log", col, decl)

    _ensure_index(conn, "ix_autopost_user_sym_tf_ts",
                  "CREATE INDEX IF NOT EXISTS ix_autopost_user_sym_tf_ts "
                  "ON autopost_log(user_id, symbol, timeframe, ts)")


def _ensure_indexes_and_triggers(conn: sqlite3.Connection) -> None:
    """
    Додаткові індекси/тригери для продуктивності та нормалізації значень.
    """
    cur = conn.cursor()
    cur.executescript("""
    -- індекси для швидких KPI/репортів
    CREATE INDEX IF NOT EXISTS ix_trades_closed_at  ON trades(closed_at);
    CREATE INDEX IF NOT EXISTS ix_signals_closed_at ON signals(closed_at);

    -- нормалізація статусу на рівні БД
    CREATE TRIGGER IF NOT EXISTS trg_trades_status_closed_up
    AFTER INSERT ON trades
    WHEN LOWER(COALESCE(NEW.status,''))='closed'
    BEGIN
      UPDATE trades SET status='CLOSED' WHERE rowid=NEW.rowid;
    END;

    CREATE TRIGGER IF NOT EXISTS trg_trades_status_closed_upd
    AFTER UPDATE OF status ON trades
    WHEN LOWER(COALESCE(NEW.status,''))='closed'
    BEGIN
      UPDATE trades SET status='CLOSED' WHERE rowid=NEW.rowid;
    END;
    """)
    conn.commit()


# ──────────────────────────────────────────────
# public entrypoints
# ──────────────────────────────────────────────
def migrate_if_needed() -> None:
    """
    Ідемпотентна міграція схеми. Безпечна до повторного запуску.
    """
    db_path = os.getenv("DB_PATH", "storage/bot.db")
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    with get_conn() as conn:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=OFF;")   # схеми без FK

        _ensure_settings(conn)
        _ensure_user_settings(conn)   # важливо перед панелями
        _ensure_signals(conn)
        _ensure_trades(conn)
        _ensure_autopost_log(conn)
        _ensure_indexes_and_triggers(conn)

        conn.commit()

    log.info("[migrate] done -> %s", db_path)


# зворотна сумісність на випадок, якщо десь звуть migrate()
def migrate() -> None:
    migrate_if_needed()
