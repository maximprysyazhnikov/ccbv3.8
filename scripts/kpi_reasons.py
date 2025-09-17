# scripts/kpi_reasons.py
from __future__ import annotations
import os, sys, sqlite3, argparse, time
from typing import Dict, List, Tuple

DEFAULT_DB = os.getenv("DB_PATH", "storage/bot.db")
DEFAULT_DAYS = 7

SIG_TS_CANDIDATES = ["ts_closed", "ts_created", "snapshot_ts", "created_at", "opened_at", "closed_at"]
TRD_TS_CANDIDATES = ["ts_closed", "closed_at", "opened_at", "created_at"]

def _cols(conn: sqlite3.Connection, table: str) -> Dict[str, str]:
    return {r[1]: (r[2] or "").upper() for r in conn.execute(f"PRAGMA table_info({table})")}

def _ts_expr(cols: Dict[str, str], candidates: List[str]) -> str | None:
    parts: List[str] = []
    for c in candidates:
        if c not in cols:
            continue
        t = cols[c]
        # INT/NUM/REAL вважаємо epoch; інакше парсимо як текстову дату
        if "INT" in t or "REAL" in t or "NUM" in t:
            parts.append(c)
        else:
            parts.append(f"strftime('%s',{c})")
    if not parts:
        return None
    if len(parts) == 1:
        return parts[0]
    return "COALESCE(" + ",".join(parts) + ")"

def _reason_expr(cols: Dict[str, str], *names: str) -> str | None:
    """NULLIF(TRIM(col),'') для 1 колонки; COALESCE(NULLIF(TRIM(a),''), NULLIF(TRIM(b),''), ...) для кількох."""
    available = [n for n in names if n in cols]
    if not available:
        return None
    if len(available) == 1:
        return f"NULLIF(TRIM({available[0]}), '')"
    inner = ",".join([f"NULLIF(TRIM({n}), '')" for n in available])
    return f"COALESCE({inner})"

def _fetch_reasons(conn: sqlite3.Connection, table: str, reason_sql: str | None,
                   days: int, ts_candidates: List[str]) -> List[Tuple[str, int]]:
    if not reason_sql:
        return []
    cols = _cols(conn, table)
    ts_sql = _ts_expr(cols, ts_candidates)
    since_ts = int(time.time()) - days * 86400

    if ts_sql:
        sql = f"""
            SELECT reason, COUNT(*) AS n FROM (
                SELECT {reason_sql} AS reason, {ts_sql} AS ts
                FROM {table}
            )
            WHERE reason IS NOT NULL AND ts IS NOT NULL AND ts >= ?
            GROUP BY reason
            ORDER BY n DESC, reason ASC
        """
        rows = conn.execute(sql, (since_ts,)).fetchall()
    else:
        sql = f"""
            SELECT {reason_sql} AS reason, COUNT(*) AS n
            FROM {table}
            WHERE {reason_sql} IS NOT NULL
            GROUP BY {reason_sql}
            ORDER BY n DESC, {reason_sql} ASC
        """
        rows = conn.execute(sql).fetchall()

    # reason може бути None після COALESCE/NULLIF — відфільтруємо тут
    out: List[Tuple[str, int]] = []
    for r in rows:
        reason, n = r[0], int(r[1])
        if reason is None or str(reason).strip() == "":
            continue
        out.append((str(reason), n))
    return out

def _print_block(title: str, rows: List[Tuple[str, int]]):
    print(f"[{title}]")
    if not rows:
        print("(no data)\n"); return
    total = sum(n for _, n in rows) or 1
    w = max(12, max((len(str(r)) for r, _ in rows), default=12))
    print(f"{'Reason'.ljust(w)}  {'N':>5}  {'Pct%':>6}")
    print("-" * (w + 15))
    for reason, n in rows:
        print(f"{str(reason).ljust(w)}  {n:5d}  {100.0*n/total:6.1f}")
    print()

def main():
    p = argparse.ArgumentParser(
        description="KPI by reasons (signals/trades). Supports positional DAYS or --days/--db flags.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("pos_days", nargs="?", type=int, help="Days window (optional)")
    p.add_argument("--days", type=int, default=None, help="Days window")
    p.add_argument("--db", type=str, default=DEFAULT_DB, help="SQLite DB path")
    args = p.parse_args()
    days = args.days if args.days is not None else (args.pos_days if args.pos_days is not None else DEFAULT_DAYS)

    print(f"KPI by reasons (last {days}d) | db={args.db}\n")
    with sqlite3.connect(args.db) as con:
        sig_cols = _cols(con, "signals")
        tr_cols  = _cols(con, "trades")

        # signals.reject_reason
        sig_reject = _fetch_reasons(
            con, "signals",
            _reason_expr(sig_cols, "reject_reason"),
            days, SIG_TS_CANDIDATES
        )
        _print_block("signals.reject_reason", sig_reject)

        # trades.reason_close (зливаємо reason_close/close_reason)
        tr_reason_sql = _reason_expr(tr_cols, "reason_close", "close_reason")
        tr_close = _fetch_reasons(con, "trades", tr_reason_sql, days, TRD_TS_CANDIDATES)
        _print_block("trades.reason_close", tr_close)

        # signals.reason_close
        sig_close = _fetch_reasons(
            con, "signals",
            _reason_expr(sig_cols, "reason_close"),
            days, SIG_TS_CANDIDATES
        )
        _print_block("signals.reason_close", sig_close)

if __name__ == "__main__":
    raise SystemExit(main())
