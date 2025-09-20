param(
  [string]$DbPath = ".\storage\bot.db"
)

$ErrorActionPreference = "Stop"

Write-Host "📂 Using DB at: $DbPath"

# 0) Переконаймося, що тека для БД існує (якщо відносний шлях — створимо)
try {
  $dbDir = Split-Path -Path $DbPath -Parent
  if ($dbDir -and -not (Test-Path $dbDir)) {
    New-Item -ItemType Directory -Path $dbDir | Out-Null
  }
} catch {
  Write-Warning "Не вдалося створити теку для БД (можливо, шлях порожній або кореневий). Продовжую..."
}

# 1) Підготуємо Python-код (ідемпотентні міграції)
$pythonCode = @'
import sys, os, sqlite3

def parse_db_path():
    # --db <path> expected
    argv = sys.argv[1:]
    if "--db" in argv:
        i = argv.index("--db")
        try:
            return argv[i+1]
        except IndexError:
            pass
    # fallback
    return "./storage/bot.db"

DB = parse_db_path()
dirn = os.path.dirname(DB)
if dirn:
    os.makedirs(dirn, exist_ok=True)

con = sqlite3.connect(DB)
cur = con.cursor()

def table_exists(name):
    row = cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone()
    return bool(row)

def table_cols(name):
    return { r[1] for r in cur.execute(f"PRAGMA table_info({name})") }

def ensure_table(sql):
    cur.execute(sql)

def ensure_column(table, col, decl):
    cols = table_cols(table)
    if col not in cols:
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")

# ── user_settings ────────────────────────────────────────────────────────────
ensure_table("CREATE TABLE IF NOT EXISTS user_settings (user_id INTEGER PRIMARY KEY)")
for col, decl in {
    "timeframe":    "TEXT DEFAULT '15m'",
    "autopost":     "INTEGER DEFAULT 0",
    "autopost_tf":  "TEXT DEFAULT '15m'",
    "autopost_rr":  "REAL DEFAULT 1.5",
    "rr_threshold": "REAL DEFAULT 1.5",
    "model_key":    "TEXT DEFAULT 'auto'",
    "locale":       "TEXT DEFAULT 'uk'",
}.items():
    ensure_column("user_settings", col, decl)

# ── signals ─────────────────────────────────────────────────────────────────
ensure_table("""
CREATE TABLE IF NOT EXISTS signals(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER,
  symbol  TEXT,
  tf      TEXT,
  direction TEXT,
  entry   REAL, sl REAL, tp REAL, rr REAL,
  ts_created INTEGER,
  ts_closed  INTEGER,
  status   TEXT,
  pnl_pct  REAL
)""")
for col, decl in {
    "user_id":    "INTEGER",
    "symbol":     "TEXT",
    "tf":         "TEXT",
    "direction":  "TEXT",
    "entry":      "REAL",
    "sl":         "REAL",
    "tp":         "REAL",
    "rr":         "REAL",
    "ts_created": "INTEGER",
    "ts_closed":  "INTEGER",
    "status":     "TEXT",
    "pnl_pct":    "REAL",
}.items():
    ensure_column("signals", col, decl)

cur.execute("CREATE INDEX IF NOT EXISTS idx_signals_user_open ON signals(user_id, status)")

# ── autopost_log ────────────────────────────────────────────────────────────
ensure_table("""
CREATE TABLE IF NOT EXISTS autopost_log(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER,
  symbol  TEXT,
  tf      TEXT,
  rr      REAL,
  ts_sent INTEGER
)""")
for col, decl in {
    "user_id": "INTEGER",
    "symbol":  "TEXT",
    "tf":      "TEXT",
    "rr":      "REAL",
    "ts_sent": "INTEGER",
}.items():
    ensure_column("autopost_log", col, decl)

cur.execute("CREATE INDEX IF NOT EXISTS idx_aplog_dedup ON autopost_log(user_id, symbol, tf, ts_sent)")

con.commit()

# ── Діагностика ─────────────────────────────────────────────────────────────
def cols(name):
    return [r[1] for r in con.execute(f"PRAGMA table_info({name})")]

print("✅ Migration OK")
print("[diag] DB_PATH:", DB)
print("[diag] user_settings:", cols("user_settings"))
print("[diag] signals:", cols("signals"))
print("[diag] autopost_log:", cols("autopost_log"))

con.close()
'@

# 2) Запишемо тимчасовий .py і виконаємо
$tmpPy = Join-Path $env:TEMP ("ccbv3_db_patch_" + [guid]::NewGuid().ToString() + ".py")
Set-Content -Path $tmpPy -Value $pythonCode -Encoding UTF8

try {
  & python $tmpPy --db $DbPath
} finally {
  # 3) Приберемо тимчасовий файл
  if (Test-Path $tmpPy) { Remove-Item $tmpPy -Force }
}
