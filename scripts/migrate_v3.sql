-- user_settings
CREATE TABLE IF NOT EXISTS user_settings (
  user_id INTEGER PRIMARY KEY,
  timeframe TEXT DEFAULT '15m',
  autopost INTEGER DEFAULT 0,
  autopost_tf TEXT DEFAULT '15m',
  autopost_rr REAL DEFAULT 1.5,
  rr_threshold REAL DEFAULT 1.5,
  model_key TEXT DEFAULT 'auto',
  locale TEXT DEFAULT 'uk'
);

-- signals
CREATE TABLE IF NOT EXISTS signals (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  symbol TEXT NOT NULL,
  tf TEXT NOT NULL,
  direction TEXT CHECK(direction IN ('LONG','SHORT')) NOT NULL,
  entry REAL NOT NULL,
  sl REAL NOT NULL,
  tp REAL NOT NULL,
  rr REAL NOT NULL,
  ts_created INTEGER NOT NULL,
  ts_closed INTEGER,
  status TEXT CHECK(status IN ('OPEN','WIN','LOSS','SKIP')) NOT NULL,
  pnl_pct REAL
);

-- autopost_log
CREATE TABLE IF NOT EXISTS autopost_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  symbol TEXT NOT NULL,
  tf TEXT NOT NULL,
  rr REAL NOT NULL,
  ts_sent INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_signals_user_open ON signals(user_id, status);
CREATE INDEX IF NOT EXISTS idx_aplog_dedup ON autopost_log(user_id, symbol, tf, ts_sent);
