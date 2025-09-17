-- 003_settings_and_indexes.sql
-- Стабілізація налаштувань і ключові індекси.
-- Запуск: sqlite3 storage/bot.db < migrations/003_settings_and_indexes.sql

BEGIN;

CREATE TABLE IF NOT EXISTS settings (
  key   TEXT PRIMARY KEY,
  value TEXT
);

-- індекси на signals (якщо таблиця існує)
CREATE INDEX IF NOT EXISTS ix_signals_closed_at ON signals(closed_at);
CREATE INDEX IF NOT EXISTS ix_signals_status    ON signals(status);
CREATE INDEX IF NOT EXISTS ix_signals_symbol    ON signals(symbol);

-- індекси на trades (якщо таблиця існує)
CREATE INDEX IF NOT EXISTS ix_trades_closed_at  ON trades(closed_at);
CREATE INDEX IF NOT EXISTS ix_trades_status     ON trades(status);
CREATE INDEX IF NOT EXISTS ix_trades_symbol     ON trades(symbol);

COMMIT;
