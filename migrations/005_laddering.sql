-- 005_laddering.sql
-- Підтримка “відер” (поштучний вхід/вихід).
-- Запуск: sqlite3 storage/bot.db < migrations/005_laddering.sql

BEGIN;

CREATE TABLE IF NOT EXISTS trade_legs (
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  trade_id  INTEGER NOT NULL,
  side      TEXT    NOT NULL,        -- 'BUY'|'SELL'
  qty       REAL    NOT NULL,
  price     REAL    NOT NULL,
  filled_at TEXT,                     -- ISO UTC
  FOREIGN KEY(trade_id) REFERENCES trades(id)
);

-- розширення таблиці trades під laddering
ALTER TABLE trades  ADD COLUMN avg_entry        REAL;
ALTER TABLE trades  ADD COLUMN filled_buckets   INTEGER;
ALTER TABLE trades  ADD COLUMN target_rrs_json  TEXT;  -- напр. '["0.5","1.0","1.5"]'

COMMIT;
