-- 004_telemetry_columns.sql
-- Додає телеметрію. УВАГА: SQLite не підтримує IF NOT EXISTS для колонок.
-- Якщо колонки вже існують — виконай idempotent-скрипт scripts/migrate.py (нижче).
-- Інакше просто застосуй цей файл.
-- Запуск: sqlite3 storage/bot.db < migrations/004_telemetry_columns.sql

BEGIN;

-- На trades
ALTER TABLE trades ADD COLUMN reason_close   TEXT;   -- 'tp','sl','neutral','reverse','manual'
ALTER TABLE trades ADD COLUMN trend_ok       INTEGER;-- 0/1
ALTER TABLE trades ADD COLUMN atr_entry      REAL;
ALTER TABLE trades ADD COLUMN ema50          REAL;
ALTER TABLE trades ADD COLUMN ema200         REAL;
ALTER TABLE trades ADD COLUMN rr_target      REAL;
ALTER TABLE trades ADD COLUMN entry_sl_dist  REAL;
ALTER TABLE trades ADD COLUMN partial_50_done INTEGER;
ALTER TABLE trades ADD COLUMN be_done         INTEGER;

-- Дзеркальні легкі поля на signals (для фільтрації/аналітики)
ALTER TABLE signals ADD COLUMN reason_close  TEXT;
ALTER TABLE signals ADD COLUMN trend_ok      INTEGER;
ALTER TABLE signals ADD COLUMN atr_entry     REAL;
ALTER TABLE signals ADD COLUMN ema50         REAL;
ALTER TABLE signals ADD COLUMN ema200        REAL;
ALTER TABLE signals ADD COLUMN rr_target     REAL;
ALTER TABLE signals ADD COLUMN entry_sl_dist REAL;

COMMIT;
