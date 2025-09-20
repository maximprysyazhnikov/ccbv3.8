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
        log.warning("[db] cannot create dir %s: %s", parent, e)

def _candidates() -> list[str]:
    env_path = os.environ.get("DB_PATH", "").strip()
    cands = []
    if env_path:
        cands.append(env_path)
    cands.append("/data/bot.db")                 # Railway volume
    cands.append(os.path.join(".", "data", "bot.db"))  # local fallback
    uniq = []
    for p in cands:
        if p not in uniq:
            uniq.append(p)
    return uniq

def _try_connect(path: str) -> Optional[sqlite3.Connection]:
    try:
        _mkparent(path)
        con = sqlite3.connect(path, timeout=30, check_same_thread=False)
        con.execute("PRAGMA journal_mode=WAL;")
        return con
    except Exception as e:
        log.warning("[db] open failed for %s: %s", path, e)
        return None

@contextlib.contextmanager
def get_conn() -> Iterator[sqlite3.Connection]:
    tried = []
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
        tried.append(path)
    raise sqlite3.OperationalError(
        "unable to open database file (all candidates failed: " + ", ".join(tried) + ")"
    )
