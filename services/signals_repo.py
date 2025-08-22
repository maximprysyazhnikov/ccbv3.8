# services/signals_repo.py
from __future__ import annotations
import os, sqlite3, time, math, json, logging
from typing import Optional, Dict, Any

log = logging.getLogger("signals_repo")

_DB_PATH = (
    os.getenv("DB_PATH")
    or os.getenv("SQLITE_PATH")
    or os.getenv("DATABASE_PATH")
    or "storage/bot.db"
)

def _conn():
    os.makedirs(os.path.dirname(_DB_PATH) or ".", exist_ok=True)
    c = sqlite3.connect(_DB_PATH, timeout=30)
    c.row_factory = sqlite3.Row
    return c

def _signals_cols() -> set[str]:
    try:
        with _conn() as c:
            cur = c.execute("PRAGMA table_info(signals)")
            return {row[1] for row in cur.fetchall()}
    except Exception:
        return set()

def _ensure_signals_schema():
    try:
        with _conn() as c:
            cur = c.cursor()
            cur.execute("PRAGMA table_info(signals)")
            cols = {row[1] for row in cur.fetchall()}
            needed = [
                ("tf",         "TEXT"),
                ("source",     "TEXT"),
                ("analysis_id","TEXT"),
                ("snapshot_ts","INTEGER"),
                ("size_usd",   "REAL"),
                ("rr",         "REAL"),
                ("status",     "TEXT"),
                ("ts_created", "INTEGER"),
                ("ts_closed",  "INTEGER"),
                ("pnl_pct",    "REAL"),
                ("sl",         "REAL"),
                ("tp",         "REAL"),
                ("details",    "TEXT"),  # JSON-рядок
            ]
            for col, typ in needed:
                if col not in cols:
                    try:
                        cur.execute(f"ALTER TABLE signals ADD COLUMN {col} {typ}")
                    except Exception:
                        pass
            c.commit()
    except Exception as e:
        log.warning("_ensure_signals_schema failed: %s", e)

_ensure_signals_schema()

def _f(v, default=None):
    try:
        vv = float(v)
        if math.isnan(vv) or math.isinf(vv):
            return default
        return vv
    except Exception:
        return default

def insert_open_signal(
    *,
    user_id: int,
    source: str = "autopost",
    symbol: str,
    timeframe: Optional[str] = None,
    tf: Optional[str] = None,
    direction: str = "NEUTRAL",
    entry: Optional[float] = None,
    stop: Optional[float] = None,
    tp: Optional[float] = None,
    rr: Optional[float] = None,
    size_usd: float = 100.0,
    analysis_id: str = "",
    snapshot_ts: Optional[int] = None,
    details: Optional[Dict[str, Any]] = None,
) -> int:
    """
    Ідемпотентна вставка OPEN-сигналу. Мапить timeframe→tf.
    Повертає lastrowid або 0 при помилці.
    """
    tf_val = (tf or timeframe or "").strip()
    if not tf_val:
        raise ValueError("insert_open_signal: 'tf'/'timeframe' is required")

    now_ts = int(time.time())
    cols = _signals_cols()

    row: Dict[str, Any] = {
        "user_id": int(user_id or 0),
        "source": source or "autopost",
        "symbol": (symbol or "").upper(),
        "tf": tf_val,
        "direction": (direction or "NEUTRAL").upper(),
        "entry": _f(entry, 0.0),
        "stop": _f(stop, 0.0),
        "tp": _f(tp, 0.0),
        "rr": _f(rr, None),
        "status": "OPEN",
        "ts_created": now_ts,
        "analysis_id": analysis_id or "",
        "snapshot_ts": int(snapshot_ts or now_ts),
        "size_usd": _f(size_usd, 100.0),
    }

    # Якщо є 'sl' у схемі — дублюємо stop у sl
    if "sl" in cols and "sl" not in row:
        row["sl"] = row["stop"]

    # details як JSON, якщо є колонка
    if details is not None and "details" in cols:
        try:
            row["details"] = json.dumps(details, ensure_ascii=False)
        except Exception:
            row["details"] = None

    # Фіксований бажаний порядок + фільтр по наявних у БД колонках
    preferred = [
        "user_id","source","symbol","tf","direction",
        "entry","stop","sl","tp","rr",
        "status","ts_created","analysis_id","snapshot_ts","size_usd","details"
    ]
    insert_cols = [c for c in preferred if c in cols and c in row]
    if not insert_cols:
        log.warning("insert_open_signal: no matching columns. Existing=%r", cols)
        return 0

    placeholders = ",".join("?" for _ in insert_cols)
    col_list = ",".join(insert_cols)
    values = [row.get(c) for c in insert_cols]

    try:
        with _conn() as c:
            cur = c.cursor()
            cur.execute(f"INSERT INTO signals ({col_list}) VALUES ({placeholders})", values)
            return int(cur.lastrowid or 0)
    except Exception as e:
        log.warning("insert_open_signal failed: %s | row=%r", e, row)
        return 0
