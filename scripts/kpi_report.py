from __future__ import annotations
import os, sqlite3, argparse
from datetime import datetime, timezone, timedelta

DB_PATH = os.getenv("DB_PATH") or "storage/bot.db"
RR_BUCKET = float(os.getenv("KPI_RR_BUCKET", "2.0"))

def _conn():
    c = sqlite3.connect(DB_PATH, timeout=30)
    c.row_factory = sqlite3.Row
    return c

def _table(c) -> str:
    row = c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name IN ('trades','signals') ORDER BY CASE name WHEN 'trades' THEN 0 ELSE 1 END LIMIT 1;").fetchone()
    return row["name"] if row else "signals"

def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")

def _daily_rows(dt_from: datetime, dt_to: datetime):
    with _conn() as c:
        table = _table(c)
        cols = {r[1] for r in c.execute(f"PRAGMA table_info({table});")}
        # часовий стовпчик
        tcol = "closed_at" if "closed_at" in cols else ("closed_at_ts" if "closed_at_ts" in cols else "updated_at")
        # RR
        rrcol = "rr_realized" if "rr_realized" in cols else ("rr_planned" if "rr_planned" in cols else ("rr" if "rr" in cols else "0"))
        # статуси закриття
        closed_check = "UPPER(status) IN ('WIN','LOSS','CLOSED')"

        rows = c.execute(f"""
            SELECT date({tcol}) AS d,
                   COUNT(*) AS trd,
                   ROUND(100.0*SUM(CASE WHEN COALESCE(pnl_usd,0) > 0 THEN 1 ELSE 0 END)/COUNT(*),2) AS wr_pct,
                   ROUND(SUM(COALESCE(pnl_usd,0)),2) AS pnl_usd,
                   ROUND(AVG(COALESCE({rrcol},0)),2) AS avg_rr,
                   SUM(CASE WHEN COALESCE({rrcol},0) >= ? THEN 1 ELSE 0 END) AS rr2_cnt,
                   ROUND(SUM(CASE WHEN COALESCE({rrcol},0) >= ? THEN COALESCE(pnl_usd,0) ELSE 0 END),2) AS pnl_rr2
            FROM {table}
            WHERE {closed_check}
              AND {tcol} BETWEEN ? AND ?
            GROUP BY d
            ORDER BY d ASC
        """, (RR_BUCKET, RR_BUCKET, _iso(dt_from), _iso(dt_to))).fetchall()
    return rows

def print_table(rows):
    print("DATE                TRD    WR%       PNL$  AVG_RR   RR2_CNT   PNL_RR2$")
    print("------------------------------------------------------------")
    for r in rows:
        d = r["d"] or ""
        print(f"{d:<20}{r['trd']:>3} {r['wr_pct']:>7} {r['pnl_usd']:>10} {r['avg_rr']:>7} {r['rr2_cnt']:>10} {r['pnl_rr2']:>11}")

def main():
    ap = argparse.ArgumentParser(description="Daily KPI report (CLOSED only)")
    ap.add_argument("--days", type=int, default=7, help="Останні N днів (поденно)")
    ap.add_argument("--from", dest="date_from", help="YYYY-MM-DD")
    ap.add_argument("--to", dest="date_to", help="YYYY-MM-DD (включно)")
    args = ap.parse_args()

    if args.date_from and args.date_to:
        dt_from = datetime.strptime(args.date_from, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        dt_to   = datetime.strptime(args.date_to, "%Y-%m-%d").replace(tzinfo=timezone.utc) + timedelta(days=1)
    else:
        dt_to = datetime.now(timezone.utc)
        dt_from = dt_to - timedelta(days=args.days)

    rows = _daily_rows(dt_from, dt_to)
    print_table(rows)

if __name__ == "__main__":
    main()
