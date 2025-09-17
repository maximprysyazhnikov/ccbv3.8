import os, sqlite3, sys

DB = os.getenv("DB_PATH", "storage/bot.db")

def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/make_neutral.py <trade_id>")
        sys.exit(1)
    tid = int(sys.argv[1])

    con = sqlite3.connect(DB); cur = con.cursor()
    cols = [r[1] for r in cur.execute("PRAGMA table_info(signals)").fetchall()]
    if "trade_id" not in cols:
        print("signals.trade_id not found — nothing to do")
        return

    row = cur.execute("SELECT id FROM signals WHERE trade_id=? ORDER BY id DESC LIMIT 1", (tid,)).fetchone()
    if row:
        sid = row[0]
        sets = []
        if "decision" in cols: sets.append("decision='NEUTRAL'")
        if "status" in cols:   sets.append("status='NEUTRAL'")
        if not sets:
            print("signals.decision/status not found — nothing to update")
            return
        cur.execute(f"UPDATE signals SET {', '.join(sets)} WHERE id=?", (sid,))
        con.commit()
        print(f"OK: updated signals.id={sid} => NEUTRAL")
    else:
        fields = ["trade_id"]
        values = [tid]
        if "decision" in cols:
            fields.append("decision"); values.append("NEUTRAL")
        if "status" in cols:
            fields.append("status"); values.append("NEUTRAL")
        try:
            ph = ",".join(["?"] * len(fields))
            cur.execute(f"INSERT INTO signals({','.join(fields)}) VALUES({ph})", values)
            con.commit()
            print(f"OK: inserted signals.id={cur.lastrowid} => NEUTRAL")
        except Exception as e:
            print(f"Insert failed (table may require more fields): {e}")
    con.close()

if __name__ == "__main__":
    main()
