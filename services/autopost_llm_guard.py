# services/autopost_llm_guard.py  (НОВИЙ ФАЙЛ)
from __future__ import annotations
import os, sqlite3, logging

log = logging.getLogger("autopost")

DB_PATH = os.getenv("DB_PATH") or "storage/bot.db"

def _get_setting_db(key: str) -> str | None:
    try:
        with sqlite3.connect(DB_PATH) as c:
            c.row_factory = sqlite3.Row
            r = c.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
            return r["value"] if r else None
    except Exception:
        return None

def _set_setting_db(key: str, value: str) -> None:
    try:
        with sqlite3.connect(DB_PATH) as c:
            c.execute(
                "INSERT INTO settings(key,value) VALUES(?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value),
            )
            c.commit()
    except Exception as e:
        log.warning("autopost guard: cannot persist %s=%s (%s)", key, value, e)

def llm_enabled() -> bool:
    # .env має пріоритет: якщо false → відрубаємо
    env_flag = os.getenv("AUTOPOST_LLM_ENABLED", "").lower()
    if env_flag in ("false", "0", "no"):
        return False
    # потім дивимось у БД (може бути 'false' після 402)
    db_flag = (_get_setting_db("autopost_llm_enabled") or "false").lower()
    return db_flag in ("true", "1", "yes")

def disable_llm(reason: str) -> None:
    _set_setting_db("autopost_llm_enabled", "false")
    os.environ["AUTOPOST_LLM_ENABLED"] = "false"  # на всякий
    log.warning("autopost: LLM disabled (%s)", reason)
