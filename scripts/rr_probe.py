import os, sqlite3
from importlib import import_module

DB = os.getenv("DB_PATH", "storage/bot.db")

def get_price(symbol: str):
    for modname in (
        "services.market",
        "services.price_provider",
        "services.binance_price",
        "services.binance",
        "services.prices",
    ):
        try:
            mod = import_module(modname)
            if hasattr(mod, "get_price"):
                return float(mod.get_price(symbol))
        except Exception:
            continue
    return None

def rr(entry, sl, px, direction='LONG', eps=1e-6):
    r = abs(entry - sl)
    if r <= eps or px is None:
        return 0.0
    return (px - entry) / r if (direction or "LONG").upper() == "LONG" else (entry - px) / r

con = sqlite3.connect(DB); cur = con.cursor()
rows = cur.execute(
    "SELECT id, symbol, direction, entry, sl FROM trades WHERE (status IS NULL OR UPPER(status)='OPEN') ORDER BY id"
).fetchall()
con.close()

print("OPEN TRADES RR snapshot:")
for tid, sym, direction, entry, sl in rows:
    px = get_price(sym)
    rrv = rr(float(entry or 0), float(sl or 0), px, direction or "LONG")
    flag = "  "
    if rrv >= 1.5:
        flag = "🔥"
    elif rrv >= 1.0:
        flag = "✅"
    print(f"{flag} id={tid:>3} {sym:<10} dir={direction:<5} entry={entry:.6f} sl={sl:.6f} px={px} RR={rrv:.2f}")
