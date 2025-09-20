# utils/db.py
from __future__ import annotations
import os
import sqlite3
import contextlib
import logging
from typing import Iterator, Optional

log = logging.getLogger("db")

def _mkparent(path: str) -> None:
    parent = os.path.dirname(path) or "."
    try:
        os.makedirs(parent, exist_ok=True)
    except Exception as e:
        # Не фатально — спробуємо інші кандидати
        log.warning("[db] cannot create dir %s: %s", parent, e)

def _candidates() -> list[str]:
    env_path = os.environ.get("DB_PATH", "").strip()
    cands = []
    if env_path:
        cands.append(env_path)
    # Найнадійніше місце на Railway — /data
    cands.append("/data/bot.db")
    # Локальний fallback (якщо немає volume)
    cands.append(os.path.join(".", "data", "bot.db"))
    # Унікалізуємо порядок
    uniq = []
    for p in cands:
        if p not in uniq:
            uniq.append(p)
    return uniq

def _try_connect(path: str) -> Optional[sqlite3.Connection]:
    try:
        _mkparent(path)
        # Якщо директорія існує, але недоступна на запис — SQLite впаде тут
        con = sqlite3.connect(path, timeout=30, check_same_thread=False)
        # Легка перевірка доступу
        con.execute("PRAGMA journal_mode=WAL;")
        return con
    except Exception as e:
        log.warning("[db] open failed for %s: %s", path, e)
        return None

@contextlib.contextmanager
def get_conn() -> Iterator[sqlite3.Connection]:
    last_err: Optional[Exception] = None
    for path in _candidates():
        con = _try_connect(path)
        if con is not None:
            try:
                log.info("[db] using %s", path)
                yield con
            finally:
                try:
                    con.close()
                except Exception:
                    pass
            return
    # Якщо сюди дійшли — жоден кандидат не відкрився
    raise sqlite3.OperationalError("unable to open database file (all candidates failed: "
                                   + ", ".join(_candidates()) + ")")
