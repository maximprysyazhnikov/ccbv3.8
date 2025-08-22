from __future__ import annotations
import os, json
from typing import List, Dict, Any

from dotenv import load_dotenv
load_dotenv()

def _parse_or_slots_from_env() -> List[Dict[str, Any]]:
    """
    Підтримує три формати:
    1) OR_SLOTS як JSON:
       OR_SLOTS=[{"key":"sk-or-AAA","model":"deepseek/deepseek-chat","base":"...","timeout":20}, ...]
    2) OR_SLOTS як простий список:
       OR_SLOTS=sk-or-AAA:deepseek/deepseek-chat,sk-or-BBB:openai/gpt-4o-mini
    3) Пара змінних через кому:
       OPENROUTER_KEYS=sk-or-AAA,sk-or-BBB
       OPENROUTER_MODEL=deepseek/deepseek-chat,openai/gpt-4o-mini
       (якщо моделей менше — копіюємо першу на всі ключі)
    """
    slots: List[Dict[str, Any]] = []

    raw = (os.getenv("OR_SLOTS", "") or "").strip()
    if raw:
        # JSON?
        if raw.startswith("["):
            try:
                data = json.loads(raw)
                for s in data:
                    key = s.get("key") or s.get("api_key")
                    model = s.get("model")
                    base = s.get("base")
                    timeout = s.get("timeout")
                    if key and model:
                        slots.append({"key": key, "model": model, "base": base, "timeout": timeout})
            except Exception:
                pass
        else:
            # simple form: key:model,key2:model2
            parts = [p.strip() for p in raw.split(",") if p.strip()]
            for p in parts:
                if ":" in p:
                    k, m = [x.strip() for x in p.split(":", 1)]
                    if k and m:
                        slots.append({"key": k, "model": m})
    # доповнюємо з OPENROUTER_KEYS / OPENROUTER_MODEL, якщо треба
    if not slots:
        keys = [k.strip() for k in (os.getenv("OPENROUTER_KEYS", "") or "").split(",") if k.strip()]
        models = [m.strip() for m in (os.getenv("OPENROUTER_MODEL", "") or "").split(",") if m.strip()]
        if keys and models:
            if len(models) < len(keys):
                models += [models[0]] * (len(keys) - len(models))
            for k, m in zip(keys, models):
                slots.append({"key": k, "model": m})

    # фільтр і підстановка дефолтів base/timeout
    base_default = os.getenv("OPENROUTER_BASE", "https://openrouter.ai/api/v1")
    timeout_default = int(os.getenv("OPENROUTER_TIMEOUT", "30") or 30)
    normalized = []
    for s in slots:
        if not (s.get("key") and s.get("model")):
            continue
        normalized.append({
            "key": s["key"],
            "model": s["model"],
            "base": s.get("base") or base_default,
            "timeout": int(s.get("timeout") or timeout_default),
        })
    return normalized

CFG: Dict[str, Any] = {
    # Telegram
    "tg_token": os.getenv("TELEGRAM_BOT_TOKEN"),
    "tg_chat_id": os.getenv("TELEGRAM_CHAT_ID"),

    # Modes
    "bot_mode": os.getenv("BOT_MODE", "polling"),
    "webhook_url": os.getenv("WEBHOOK_URL"),
    "port": int(os.getenv("PORT", "8080") or 8080),

    # Time / Locale
    "tz": os.getenv("TZ_NAME", "Europe/Kyiv"),
    "default_locale": os.getenv("DEFAULT_LOCALE", "uk"),

    # Symbols
    "symbols": [s.strip() for s in (os.getenv("MONITORED_SYMBOLS", "BTCUSDT") or "").split(",") if s.strip()],

    # Analysis
    "analyze_timeframe": os.getenv("ANALYZE_TIMEFRAME", "15m"),
    "analyze_limit": int(os.getenv("ANALYZE_LIMIT", "150") or 150),

    # OpenRouter (multi-slot)
    "or_slots": _parse_or_slots_from_env(),

    # For backward compat (деякі місця ще читають ці значення)
    "or_base": os.getenv("OPENROUTER_BASE", "https://openrouter.ai/api/v1"),
    "or_timeout": int(os.getenv("OPENROUTER_TIMEOUT", "30") or 30),

    # AutoPost
    "autopost_cron": os.getenv("AUTOPOST_SCAN_CRON", ""),   # якщо пусто — використовуємо інтервал
    "autopost_interval_sec": int(os.getenv("AUTOPOST_INTERVAL_SEC", "300") or 300),
    "autopost_cooldown_min": int(os.getenv("AUTOPOST_COOLDOWN_MIN", "30") or 30),
}

# Валідації
if not CFG["tg_token"]:
    raise RuntimeError("TELEGRAM_BOT_TOKEN is missing in .env")

# Для діагностики у логах (за бажання)
def debug_print_cfg():
    try:
        slots = [{"model": s["model"], "base": s.get("base")} for s in CFG.get("or_slots", [])]
        print(f"[CFG] symbols={CFG['symbols']} | or_slots={slots} | tz={CFG['tz']} | analyze_limit={CFG['analyze_limit']}")
    except Exception:
        pass
