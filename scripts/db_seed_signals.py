# scripts/db_seed_signals.py
from __future__ import annotations
import os, sqlite3, time, argparse, random
from datetime import datetime, timedelta

DB_PATH = (
    os.getenv("DB_PATH")
    or os.getenv("SQLITE_PATH")
    or os.getenv("DATABASE_PATH")
    or "storage/bot.db"
)

def _conn():
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    c = sqlite3.connect(DB_PATH, timeout=30)
    c.row_factory = sqlite3.Row
    return c

def ensure_tables():
    with _conn() as conn:
        cur = conn.cursor()
        # мінімальні поля, що ми використовуємо в боті
        cur.execute("""
        CREATE TABLE IF NOT EXISTS signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            symbol TEXT,
            status TEXT,            -- 'WIN' | 'LOSS' | 'OPEN'
            rr REAL,                -- risk/reward
            pnl_pct REAL,           -- % PnL (може бути 0 для заглушки)
            entry REAL,
            stop REAL,
            tp REAL,
            ts_created INTEGER,
            ts_closed INTEGER
        )
        """)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS user_settings (
            user_id INTEGER PRIMARY KEY,
            timeframe TEXT,
            autopost INTEGER,
            autopost_tf TEXT,
            autopost_rr REAL,
            rr_threshold REAL,
            model_key TEXT,
            locale TEXT
        )
        """)
        conn.commit()

def seed(user_id: int, days: int, n: int, rr_min: float, symbol: str):
    random.seed(42)
    now = int(time.time())

    rows = []
    # зробимо половину WIN, половину LOSS (заокруглимо вниз для парності)
    n = max(1, n)
    n_win = n // 2
    n_loss = n - n_win

    def mk_trade(day_offset: int, is_win: bool, rr_target: float):
        # Час створення/закриття у межах дня
        dt_close = datetime.utcnow() - timedelta(days=day_offset, hours=random.randint(0, 20))
        dt_open = dt_close - timedelta(minutes=random.randint(5, 240))
        ts_created = int(dt_open.timestamp())
        ts_closed  = int(dt_close.timestamp())

        # Прості рівні для заглушки, щоб RR вийшов ≈ rr_target
        # LONG-сценарій (для WIN: tp далі, для LOSS: sl ближче)
        entry = round(random.uniform(1.0, 100.0), 4)
        risk  = round(entry * 0.01, 4)               # 1% від ціни як ризик
        reward= round(risk * rr_target, 4)

        if is_win:
            stop = round(entry - risk, 4)
            tp   = round(entry + reward, 4)
            status = "WIN"
            pnl_pct = round(rr_target * 1.0, 2)      # умовно +RR%
        else:
            stop = round(entry - reward, 4)          # втрати більше — щоб RR < 1 для LOSS у реалі
            tp   = round(entry + risk, 4)
            status = "LOSS"
            pnl_pct = round(-1.0 * rr_target, 2)

        rr = rr_target
        return (user_id, symbol, status, rr, pnl_pct, entry, stop, tp, ts_created, ts_closed)

    # розкидаємо угоди по різних днях у межах вікна
    for i in range(n_win):
        day = random.randint(0, max(0, days - 1))
        rr_t = round(max(rr_min, random.uniform(rr_min, rr_min + 1.5)), 2)
        rows.append(mk_trade(day, True, rr_t))

    for i in range(n_loss):
        day = random.randint(0, max(0, days - 1))
        rr_t = round(max(rr_min, random.uniform(rr_min, rr_min + 1.5)), 2)
        rows.append(mk_trade(day, False, rr_t))

    # перемішаємо, щоб порядок був різний
    random.shuffle(rows)

    with _conn() as conn:
        cur = conn.cursor()
        cur.executemany("""
            INSERT INTO signals (user_id, symbol, status, rr, pnl_pct, entry, stop, tp, ts_created, ts_closed)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, rows)
        conn.commit()

def main():
    ap = argparse.ArgumentParser(description="Seed test WIN/LOSS signals")
    ap.add_argument("--user", type=int, required=True, help="Telegram user_id")
    ap.add_argument("--days", type=int, default=7, help="Window of days to backfill (default 7)")
    ap.add_argument("--n", type=int, default=6, help="Number of trades to create (default 6)")
    ap.add_argument("--rr", type=float, default=2.0, help="Minimum RR to target (default 2.0)")
    ap.add_argument("--symbol", type=str, default="BTCUSDT", help="Symbol to use (default BTCUSDT)")
    args = ap.parse_args()

    ensure_tables()
    seed(args.user, args.days, args.n, args.rr, args.symbol)
    print(f"OK: seeded {args.n} trades for user {args.user} over last {args.days} days (RR≥{args.rr}, symbol={args.symbol})")
    print(f"DB: {DB_PATH}")

if __name__ == "__main__":
    main()
