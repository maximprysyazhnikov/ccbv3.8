# services/kpi.py
from __future__ import annotations
import os, sqlite3, time

DB_PATH = os.getenv("DB_PATH","storage/bot.db")

def kpi_summary(days: int = 7, table: str = "trades") -> str:
    con = sqlite3.connect(DB_PATH); cur = con.cursor()
    since = int(time.time()) - days*24*3600
    # гнучкі колонки
    cols = [r[1] for r in cur.execute(f"PRAGMA table_info({table})")]
    rr_col   = "rr_realized" if "rr_realized" in cols else ("rr" if "rr" in cols else None)
    pnl_col  = "pnl_usd" if "pnl_usd" in cols else ("pnl" if "pnl" in cols else None)
    ts_pred  = "CAST(strftime('%s',closed_at) AS INTEGER)>=?" if "closed_at" in cols else (f"{'ts_closed' if 'ts_closed' in cols else 'ts_created'} >= ?")
    q = f"""
      SELECT symbol,
             COUNT(*) AS n,
             ROUND(100.0*SUM(CASE WHEN COALESCE({pnl_col},0)>0 THEN 1 ELSE 0 END)/COUNT(*),1) AS win_pct,
             ROUND(AVG(COALESCE({rr_col},0)),2) AS avg_rr,
             ROUND(SUM(COALESCE({pnl_col},0)),2) AS pnl_usd
      FROM {table}
      WHERE {ts_pred}
      GROUP BY symbol
      ORDER BY symbol
    """
    rows = cur.execute(q,(since,)).fetchall()
    con.close()

    head = f"KPI ({table}) last {days}d"
    if not rows:
        return head + "\n— немає даних за період."
    out = [head, "────────────────────────────────────────", "Symbol    N   Win%  AvgRR   PnL_USD", "────────────────────────────────────────"]
    tot_n=tot_win=0; tot_pnl=0.0; rr_acc=0.0; rr_cnt=0
    for s,n,win,avg_rr,pnl in rows:
        out.append(f"{s:8} {int(n):3} {win:5.1f}  {avg_rr:5.2f}  {pnl:8.2f}")
        tot_n += int(n); tot_win += round(win*int(n)/100.0,2); tot_pnl += float(pnl or 0.0)
        if avg_rr is not None: rr_acc += float(avg_rr or 0.0); rr_cnt += 1
    wr_tot = (tot_win / tot_n * 100.0) if tot_n else 0.0
    avg_rr_tot = (rr_acc / rr_cnt) if rr_cnt else 0.0
    out += ["────────────────────────────────────────", f"TOTAL     {tot_n:3} {wr_tot:5.1f}  {avg_rr_tot:5.2f}  {tot_pnl:8.2f}"]
    return "\n".join(out)
