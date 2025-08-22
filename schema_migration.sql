-- v2 → v3 hybrid migration (idempotent)

-- user_settings (v2 already); add locale/model_key if missing
CREATE TABLE IF NOT EXISTS user_settings (
  user_id TEXT PRIMARY KEY,
  timeframe TEXT DEFAULT '15m',
  autopost INTEGER DEFAULT 0,
  rr_threshold REAL DEFAULT 1.5,
  conf_threshold INTEGER DEFAULT 75,
  model_key TEXT DEFAULT 'auto',
  locale TEXT DEFAULT 'ua',
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- signals (new in v3)
CREATE TABLE IF NOT EXISTS signals (
  uuid TEXT PRIMARY KEY,
  ts TIMESTAMP NOT NULL,
  symbol TEXT NOT NULL,
  timeframe TEXT NOT NULL,
  model TEXT NOT NULL,
  direction TEXT,
  entry REAL,
  sl REAL,
  tp REAL,
  rr REAL,
  confidence INTEGER,
  report_path TEXT
);

-- outcomes (new in v3)
CREATE TABLE IF NOT EXISTS outcomes (
  uuid TEXT PRIMARY KEY,
  mfe REAL,
  mae REAL,
  progress REAL,
  status TEXT,
  closed_ts TIMESTAMP
);
