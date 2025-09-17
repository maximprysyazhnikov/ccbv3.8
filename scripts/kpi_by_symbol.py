# scripts/kpi_by_symbol.py
from __future__ import annotations
import os, sqlite3, time, argparse, math
from collections import defaultdict

def env_int(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, str(default)).strip())
    except Exception:
        return default

def has_col(cur: sqlite3.Cursor, table: str, col: str) -> bool:
    rows = cur.execute(f"PRAGMA table_info({table})").fetchall()
    cols = {r[1] for r in rows}
    return col in cols

def fmt(n, width=0, prec=2):
    if n is None:
        s = "-"
    elif isinstance(n, int):
        s = f"{n}"
    else:
        s = f"{n:.{prec}f}"
    return s if width <= 0 else s.rjust(width)

def rr_bucket_label(rr: float | None, step: float) -> str:
    if rr is None or math.isnan(rr):
        return "nan"
    # симпатичні категорії: …<-1, -1..0, 0..1, 1..2, 2..3, 3..5, 5+
    edges = [-1, 0, 1, 2, 3, 5]
    for i, e in enumerate(edges):
        if rr < e:
            if i == 0:
                return "<-1R"
            lo = edges[i-1]
            return f"{lo}..{e}R"
    return ">=5R"

def main():
    parser = argparse.ArgumentParser(description="KPI by symbol")
    parser.add_argument("--table", choices=["trades", "signals"], default="trades",
                        help="Яку таблицю аналізувати (default: trades)")
    parser.add_argument("--days", type=int, default=env_int("KPI_DAYS", 7),
                        help="Скільки днів назад враховувати (default: KPI_DAYS)")
    parser.add_argument("--rr-bucket", type=float, default=float(os.getenv("KPI_RR_BUCKET", "2")),
                        help="Крок бакетів RR (використовується лише для альтернативних схем)")
    parser.add_argument("--db", default=os.getenv("DB_PATH", "storage/bot.db"),
                        help="Шлях до SQLite (default: DB_PATH)")
    args = parser.parse_args()

    con = sqlite3.connect(args.db)
    cur = con.cursor()

    now = int(time.time())
    since_ts = now - args.days * 86400

    if args.table == "trades":
        # визначимо доступні колонки
        rr_real_col = "rr_realized" if has_col(cur, "trades", "rr_realized") else "rr"
        pnl_col = "pnl_usd" if has_col(cur, "trades", "pnl_usd") else ("pnl" if has_col(cur, "trades", "pnl") else None)
        ts_col = "ts_closed" if has_col(cur, "trades", "ts_closed") else None
        closed_at_col = "closed_at" if has_col(cur, "trades", "closed_at") else None
        status_col = "status" if has_col(cur, "trades", "status") else None

        # побудуємо where по часу
        time_pred = "1=1"
        params = []
        if ts_col:
            time_pred = f"COALESCE({ts_col}, CAST(strftime('%s',{closed_at_col}) AS INTEGER)) >= ?"
            params.append(since_ts)
        elif closed_at_col:
            time_pred = f"CAST(strftime('%s',{closed_at_col}) AS INTEGER) >= ?"
            params.append(since_ts)

        # лише закриті
        status_pred = "1=1"
        if status_col:
            status_pred = f"UPPER({status_col})='CLOSED'"

        base_sql = f"""
            SELECT symbol,
                   {rr_real_col},
                   {pnl_col if pnl_col else '0'}
            FROM trades
            WHERE {status_pred} AND {time_pred}
        """
        rows = cur.execute(base_sql, params).fetchall()

        per = defaultdict(lambda: {"n":0,"w":0,"l":0,"rr_sum":0.0,"pnl_sum":0.0,"buckets":defaultdict(int)})
        for sym, rr_v, pnl_v in rows:
            rr = None
            try:
                rr = float(rr_v) if rr_v is not None else None
            except Exception:
                rr = None
            pnl = float(pnl_v or 0.0)

            d = per[sym]
            d["n"] += 1
            if rr is not None and rr > 0:
                d["w"] += 1
            else:
                d["l"] += 1
            d["rr_sum"] += (rr or 0.0)
            d["pnl_sum"] += pnl

            lab = rr_bucket_label(rr, args.rr_bucket)
            d["buckets"][lab] += 1

        # друк
        syms = sorted(per.keys())
        print(f"KPI (trades) last {args.days}d | db={args.db}")
        print("-"*80)
        print(f"{'Symbol':8} {'N':>4} {'Win%':>6} {'AvgRR':>7} {'PnL_USD':>10}  Buckets")
        print("-"*80)
        tot_n=tot_w=0; tot_rr=0.0; tot_pnl=0.0
        for s in syms:
            d = per[s]
            n,w,l = d["n"], d["w"], d["l"]
            winp = (100.0*w/n) if n else 0.0
            avgrr = (d["rr_sum"]/n) if n else 0.0
            pnl = d["pnl_sum"]
            # впорядкована стрічка бакетів
            order = ["<-1R","-1..0R","0..1R","1..2R","2..3R","3..5R",">=5R","nan"]
            btxt = " ".join([f"{k}:{d['buckets'].get(k,0)}" for k in order if d["buckets"].get(k,0)])
            print(f"{s:8} {n:4d} {winp:6.1f} {avgrr:7.2f} {pnl:10.2f}  {btxt}")
            tot_n += n; tot_w += w; tot_rr += d["rr_sum"]; tot_pnl += pnl
        if tot_n:
            print("-"*80)
            print(f"{'TOTAL':8} {tot_n:4d} {100.0*tot_w/tot_n:6.1f} {tot_rr/tot_n:7.2f} {tot_pnl:10.2f}")

    else:
        # signals
        rr_col = "rr_real" if has_col(cur, "signals", "rr_real") else ("rr" if has_col(cur,"signals","rr") else None)
        pnl_col = "pnl_usd" if has_col(cur, "signals", "pnl_usd") else None
        ts_close = "ts_closed" if has_col(cur, "signals", "ts_closed") else None
        closed_at = "closed_at" if has_col(cur, "signals", "closed_at") else None
        status_col = "status" if has_col(cur, "signals", "status") else None

        time_pred = "1=1"
        params = []
        if ts_close:
            time_pred = f"{ts_close} >= ?"
            params.append(since_ts)
        elif closed_at:
            time_pred = f"CAST(strftime('%s',{closed_at}) AS INTEGER) >= ?"
            params.append(since_ts)

        status_pred = "1=1"
        if status_col:
            status_pred = "UPPER(status)='CLOSED'"

        if rr_col is None:
            rr_expr = "NULL"
        else:
            rr_expr = rr_col

        pnl_expr = pnl_col if pnl_col else "0"

        base_sql = f"""
            SELECT symbol, {rr_expr}, {pnl_expr}
            FROM signals
            WHERE {status_pred} AND {time_pred}
        """
        rows = cur.execute(base_sql, params).fetchall()

        per = defaultdict(lambda: {"n":0,"w":0,"l":0,"rr_sum":0.0,"pnl_sum":0.0,"buckets":defaultdict(int)})
        for sym, rr_v, pnl_v in rows:
            rr = None
            try:
                rr = float(rr_v) if rr_v is not None else None
            except Exception:
                rr = None
            pnl = float(pnl_v or 0.0)

            d = per[sym]
            d["n"] += 1
            if rr is not None and rr > 0:
                d["w"] += 1
            else:
                d["l"] += 1
            d["rr_sum"] += (rr or 0.0)
            d["pnl_sum"] += pnl
            lab = rr_bucket_label(rr, args.rr_bucket)
            d["buckets"][lab] += 1

        syms = sorted(per.keys())
        print(f"KPI (signals) last {args.days}d | db={args.db}")
        print("-"*80)
        print(f"{'Symbol':8} {'N':>4} {'Win%':>6} {'AvgRR':>7} {'PnL_USD':>10}  Buckets")
        print("-"*80)
        tot_n=tot_w=0; tot_rr=0.0; tot_pnl=0.0
        for s in syms:
            d = per[s]; n,w,l = d["n"], d["w"], d["l"]
            winp = (100.0*w/n) if n else 0.0
            avgrr = (d["rr_sum"]/n) if n else 0.0
            pnl = d["pnl_sum"]
            order = ["<-1R","-1..0R","0..1R","1..2R","2..3R","3..5R",">=5R","nan"]
            btxt = " ".join([f"{k}:{d['buckets'].get(k,0)}" for k in order if d["buckets"].get(k,0)])
            print(f"{s:8} {n:4d} {winp:6.1f} {avgrr:7.2f} {pnl:10.2f}  {btxt}")
            tot_n += n; tot_w += w; tot_rr += d["rr_sum"]; tot_pnl += pnl
        if tot_n:
            print("-"*80)
            print(f"{'TOTAL':8} {tot_n:4d} {100.0*tot_w/tot_n:6.1f} {tot_rr/tot_n:7.2f} {tot_pnl:10.2f}")

    con.close()

if __name__ == "__main__":
    main()
