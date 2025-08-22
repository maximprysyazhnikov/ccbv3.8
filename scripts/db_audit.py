# scripts/db_audit.py
from __future__ import annotations
import os, sys, sqlite3, time, argparse
from datetime import datetime, timedelta

DEF_DB = (
    os.getenv("DB_PATH")
    or os.getenv("SQLITE_PATH")
    or os.getenv("DATABASE_PATH")
    or "storage/bot.db"
)

def connect(db_path: str) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn

def fetch(conn: sqlite3.Connection, sql: str, params: tuple = ()):
    cur = conn.cursor()
    cur.execute(sql, params)
    return cur.fetchall()

def one(conn: sqlite3.Connection, sql: str, params: tuple = ()):
    cur = conn.cursor()
    cur.execute(sql, params)
    r = cur.fetchone()
    return (r[0] if r else None)

def fmt(n):
    try:
        return f"{float(n):,.2f}".replace(",", " ")
    except:
        return str(n)

def section(title: str):
    print("\n" + "="*8 + " " + title + " " + "="*8)

def integrity(conn: sqlite3.Connection):
    section("INTEGRITY")
    try:
        res = one(conn, "PRAGMA integrity_check")
        print("PRAGMA integrity_check:", res)
    except Exception as e:
        print("integrity_check error:", e)

def schema(conn: sqlite3.Connection):
    section("SCHEMA")
    rows = fetch(conn, """
        SELECT name, type, sql FROM sqlite_master
        WHERE type IN ('table','view') AND name NOT LIKE 'sqlite_%'
        ORDER BY type, name
    """)
    for r in rows:
        print(f"- {r['type']}: {r['name']}")
    # мінімум потрібні таблиці
    must = ["user_settings", "signals"]
    missing = [m for m in must if not any(r["name"]==m for r in rows)]
    if missing:
        print("⚠️ Missing tables:", ", ".join(missing))
    else:
        print("✅ Required tables present")

def users_overview(conn: sqlite3.Connection):
    section("USERS (autopost/settings)")
    rows = fetch(conn, """
        SELECT user_id,
               COALESCE(autopost,0) AS autopost,
               COALESCE(timeframe,'') AS tf,
               COALESCE(autopost_tf,'') AS ap_tf,
               COALESCE(autopost_rr, rr_threshold, 1.5) AS ap_rr,
               COALESCE(rr_threshold,1.5) AS rr_min,
               COALESCE(model_key,'auto') AS model_key,
               COALESCE(locale,'uk') AS locale
        FROM user_settings
        ORDER BY user_id
    """)
    if not rows:
        print("— user_settings: 0 записів")
        return
    on_cnt = sum(1 for r in rows if r["autopost"])
    print(f"users total: {len(rows)} | autopost ON: {on_cnt}")
    for r in rows[:12]:
        print(f"  • {r['user_id']} | autopost={r['autopost']} | tf={r['tf'] or '-'} | ap_tf={r['ap_tf'] or '-'} | ap_rr={r['ap_rr']} | rr_min={r['rr_min']} | model={r['model_key']} | loc={r['locale']}")

def signals_stats(conn: sqlite3.Connection, days: int):
    section(f"SIGNALS last {days}d (WIN/LOSS stats)")
    t1 = int(time.time()); t0 = t1 - days*86400
    # підрахунки
    rows = fetch(conn, """
        SELECT status,
               COUNT(*) AS n,
               AVG(COALESCE(rr,0)) AS rr_avg,
               AVG(COALESCE(pnl_pct,0)) AS pnl_avg
        FROM signals
        WHERE COALESCE(ts_closed, ts_created, 0) BETWEEN ? AND ?
        GROUP BY status
        ORDER BY status
    """, (t0, t1))
    total = sum(r["n"] for r in rows) if rows else 0
    print("total trades:", total)
    for r in rows:
        print(f"  {r['status']:<5} | n={r['n']:<4} | rr_avg={fmt(r['rr_avg'])} | pnl_avg={fmt(r['pnl_avg'])}%")

    # winrate з урахуванням RR-порогу користувача
    rows = fetch(conn, """
        SELECT s.user_id,
               SUM(CASE WHEN s.status='WIN'  THEN 1 ELSE 0 END) AS wins,
               SUM(CASE WHEN s.status='LOSS' THEN 1 ELSE 0 END) AS losses,
               COUNT(*) AS n,
               AVG(COALESCE(s.rr,0)) AS rr_avg,
               AVG(COALESCE(s.pnl_pct,0)) AS pnl_avg
        FROM signals s
        LEFT JOIN user_settings u ON u.user_id=s.user_id
        WHERE COALESCE(s.ts_closed, s.ts_created, 0) BETWEEN ? AND ?
          AND COALESCE(s.rr,0) >= COALESCE(u.rr_threshold, 1.5)
          AND s.status IN ('WIN','LOSS')
        GROUP BY s.user_id
        ORDER BY n DESC
    """, (t0, t1))
    if not rows:
        print("— немає сигналів з RR-фільтром за цей період.")
    else:
        print("by user (RR filtered by user_settings.rr_threshold):")
        for r in rows[:20]:
            wr = (100.0 * r["wins"] / r["n"]) if r["n"] else 0.0
            print(f"  uid={r['user_id']}: n={r['n']}, win={r['wins']}, loss={r['losses']}, winrate={fmt(wr)}%, rr_avg={fmt(r['rr_avg'])}, pnl_avg={fmt(r['pnl_avg'])}%")

def anomalies(conn: sqlite3.Connection, days: int):
    section("ANOMALIES & DATA QUALITY")
    t1 = int(time.time()); t0 = t1 - days*86400

    def show(label, sql, params=()):
        rows = fetch(conn, sql, params)
        print(f"- {label}: {len(rows)}")
        for r in rows[:10]:
            try:
                rid = r["id"] if "id" in r.keys() else "?"
            except:
                rid = "?"
            print("   •", dict(r))

    # 1) Закриті без статусу або без ts_closed
    show("closed but missing status", """
        SELECT id, user_id, symbol, status, ts_created, ts_closed
        FROM signals
        WHERE status NOT IN ('WIN','LOSS') AND ts_closed IS NOT NULL
          AND COALESCE(ts_closed,0) BETWEEN ? AND ?
    """, (t0, t1))

    # 2) Відсутні SL/TP/price (якщо поля є)
    try:
        show("missing SL/TP/entry", """
            SELECT id, user_id, symbol, entry, sl, tp, rr
            FROM signals
            WHERE (entry IS NULL OR sl IS NULL OR tp IS NULL)
              AND COALESCE(ts_created,0) BETWEEN ? AND ?
        """, (t0, t1))
    except Exception:
        pass

    # 3) RR <= 0 або NaN
    show("invalid RR (<=0 or NULL)", """
        SELECT id, user_id, symbol, rr, status
        FROM signals
        WHERE (rr IS NULL OR rr<=0)
          AND COALESCE(ts_created,0) BETWEEN ? AND ?
    """, (t0, t1))

    # 4) Дублі (symbol + ts_created близько в часі)
    show("possible duplicates (same user, symbol, +/-60s)", """
        SELECT a.id AS id_a, b.id AS id_b, a.user_id, a.symbol, a.ts_created AS t_a, b.ts_created AS t_b
        FROM signals a
        JOIN signals b
          ON a.user_id=b.user_id AND a.symbol=b.symbol
         AND a.id < b.id
         AND ABS(COALESCE(a.ts_created,0) - COALESCE(b.ts_created,0)) <= 60
        WHERE COALESCE(a.ts_created,0) BETWEEN ? AND ?
    """, (t0, t1))

    # 5) Орфани: сигнали без користувача у user_settings
    show("orphan signals (no user_settings row)", """
        SELECT s.id, s.user_id, s.symbol, s.status
        FROM signals s
        LEFT JOIN user_settings u ON u.user_id = s.user_id
        WHERE u.user_id IS NULL
        LIMIT 100
    """)

def indexes(conn: sqlite3.Connection):
    section("INDEX SUGGESTIONS")
    # запропонувати корисні індекси, якщо їх нема
    have = {r["name"] for r in fetch(conn, "PRAGMA index_list('signals')")}
    want = {
        "idx_signals_user_time": "CREATE INDEX idx_signals_user_time ON signals(user_id, ts_created)",
        "idx_signals_status": "CREATE INDEX idx_signals_status ON signals(status, ts_created)",
        "idx_signals_symbol_time": "CREATE INDEX idx_signals_symbol_time ON signals(symbol, ts_created)"
    }
    for name, sql in want.items():
        print(f"- {name}: {'OK' if name in have else 'MISSING'}")

def main():
    ap = argparse.ArgumentParser(description="CryptoCat DB audit / win-loss stats")
    ap.add_argument("--db", default=DEF_DB, help="Path to sqlite DB (env DB_PATH by default)")
    ap.add_argument("--days", type=int, default=30, help="Window for stats/anomalies")
    args = ap.parse_args()

    print(f"DB: {args.db}")
    with connect(args.db) as conn:
        integrity(conn)
        schema(conn)
        users_overview(conn)
        signals_stats(conn, args.days)
        anomalies(conn, args.days)
        indexes(conn)

if __name__ == "__main__":
    main()
