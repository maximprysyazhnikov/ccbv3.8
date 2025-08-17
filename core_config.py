# core_config.py
from __future__ import annotations
import os
from dotenv import load_dotenv

# ── Load .env ─────────────────────────────────────────────────────────────────
load_dotenv()

# ── Telegram ──────────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
USER_ID = os.getenv("TELEGRAM_USER_ID", "")  # опційно: для прямих повідомлень

# ── Binance ───────────────────────────────────────────────────────────────────
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY", "")
BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET", "")

# ── Universe / монети / фільтри ───────────────────────────────────────────────
# Приклад у .env: MONITORED_SYMBOLS=BTCUSDT,ETHUSDT,SOLUSDT
MONITORED_SYMBOLS = [
    s.strip()
    for s in os.getenv("MONITORED_SYMBOLS", "BTCUSDT,ETHUSDT").split(",")
    if s.strip()
]
UNIVERSE_MIN_QVOL_USD = float(os.getenv("UNIVERSE_MIN_QVOL_USD", "1000000"))

# ── Таймзона ──────────────────────────────────────────────────────────────────
TZ_NAME = os.getenv("TZ_NAME", "Europe/Kyiv")

# ── Таймфрейм / глибина для аналізу ───────────────────────────────────────────
ANALYZE_TIMEFRAME = os.getenv("ANALYZE_TIMEFRAME", "1h")  # 1m/5m/15m/1h/4h/1d
try:
    ANALYZE_LIMIT = int(os.getenv("ANALYZE_LIMIT", "150"))
except ValueError:
    ANALYZE_LIMIT = 150

# ── LLM: OpenRouter (хмарна) + локальна ───────────────────────────────────────
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE    = os.getenv("OPENROUTER_BASE", "https://openrouter.ai/api/v1")
OPENROUTER_MODEL   = os.getenv("OPENROUTER_MODEL", "deepseek/deepseek-chat")

# Локальна LLM (LM Studio / Ollama зі сумісним API)
LOCAL_LLM_BASE  = os.getenv("LOCAL_LLM_BASE", "http://127.0.0.1:1234/v1")
LOCAL_LLM_MODEL = os.getenv("LOCAL_LLM_MODEL", "gpt-3.5-turbo")

# ── Таймаути (сек) ────────────────────────────────────────────────────────────
def _float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default

LLM_TIMEOUT         = _float_env("LLM_TIMEOUT", 45.0)
OPENROUTER_TIMEOUT  = _float_env("OPENROUTER_TIMEOUT", LLM_TIMEOUT)
LOCAL_LLM_TIMEOUT   = _float_env("LOCAL_LLM_TIMEOUT", LLM_TIMEOUT)

# ── Реєстр сигналів (анти-дубль / протухання) ─────────────────────────────────
ALERT_MIN_COOLDOWN_MIN = int(os.getenv("ALERT_MIN_COOLDOWN_MIN", "10"))
ALERT_MAX_AGE_MIN      = int(os.getenv("ALERT_MAX_AGE_MIN", "720"))  # 12 год

# ── Analysis toggles ──────────────────────────────────────────────────────────
# Використання стакана заявок (ордербука)
USE_ORDERBOOK = False

# Півоти: можеш вмикати один або обидва
USE_CLASSIC_PIVOTS = False
USE_FIB_PIVOTS     = True

# Компактний режим:
# True  = надсилаємо GPT тільки summary (економія токенів)
# False = повний Markdown-звіт (зручніше для людини)
COMPACT_MODE = False

# Кількість барів для аналізу (наприклад, 10 барів на TF=1h → 10 годин)
ANALYZE_BARS = int(os.getenv("ANALYZE_BARS", 10))

# ── Зручні синоніми ───────────────────────────────────────────────────────────
DEFAULT_TIMEFRAME = ANALYZE_TIMEFRAME

# ── Перевірки / логування ─────────────────────────────────────────────────────
if not TELEGRAM_BOT_TOKEN:
    raise ValueError("❌ TELEGRAM_BOT_TOKEN is missing in .env")

if not BINANCE_API_KEY or not BINANCE_API_SECRET:
    print("[config] ⚠️ Binance API keys are missing — data fetching may fail.")
