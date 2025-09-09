-- trades: executed trades tracking (simulation-friendly)
CREATE TABLE IF NOT EXISTS trades (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  signal_id INTEGER,
  symbol TEXT,
  timeframe TEXT,
  direction TEXT CHECK(direction IN ('LONG','SHORT')),
  entry REAL,
  sl REAL,
  tp REAL,
  opened_at TEXT,
  closed_at TEXT,
  close_price REAL,
  close_reason TEXT,            -- 'TP'|'SL'|'NEUTRAL_CLOSE'|'MANUAL'|'CANCEL'
  size_usd REAL DEFAULT 100.0,  -- simulated USD size per trade
  fees_bps INTEGER DEFAULT 10,  -- round-trip fees in bps (e.g., 10 = 0.10%)
  pnl_usd REAL,
  pnl_pct REAL,
  rr_planned REAL,
  rr_realized REAL,
  status TEXT CHECK(status IN ('OPEN','WIN','LOSS','CLOSED')),
  FOREIGN KEY(signal_id) REFERENCES signals(id)
);
CREATE INDEX IF NOT EXISTS idx_trades_open ON trades(symbol, timeframe, status);

-- lightweight app settings
CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value TEXT
);
