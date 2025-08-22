# HYBRID MIGRATION — v2 → v3 (hybrid mode)

Мета: плавний перехід без лому. Залишаємо весь функціонал v2, додаємо v3‑фічі під прапорцями.

## Ключова ідея
- `V3_FEATURES=true` в `.env` → увімкнути нові модулі (stats/trader).
- Схема БД доповнюється, але **не ламає** існуючі таблиці.
- Команди v3 (`/stats`, `/modelrank`, `/orders`) працюють лише якщо `V3_FEATURES=true`.

## Кроки
1) Онови `.env` (див. `.env.example.hybrid`).  
2) Виконай `schema_migration.sql` (додає таблиці `signals`, `outcomes`, і колонки за потреби).  
3) Поклади нові файли у `stats/`, `trader/`, `utils/ids.py`.  
4) Підключи хендлери v3 у `telegram_bot/handlers.py` **лише якщо** `V3_FEATURES=true`.  
5) Smoke‑тест: `/panel → /ai BTCUSDT 15m → /analyze → /stats → /modelrank`.  

## Backward‑compat
- Якщо `V3_FEATURES=false` — бот працює як v2 (команди v3 сховані).  
- Дані `signals`/`outcomes` не заважають v2 ігнорувати v3‑логіку.

## Acceptance
- Бот стартує з незміненою v2‑конфігурацією.  
- При `V3_FEATURES=true` — команди v3 видимі й не падають навіть без історії.  
- Схема БД сумісна в обидва боки (можна вимкнути v3 без міграцій назад).
