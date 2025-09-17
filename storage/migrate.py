# storage/migrate.py
from __future__ import annotations

import os
import logging
from typing import Optional

__all__ = ["migrate"]

log = logging.getLogger("migrate")


def migrate(db_path: Optional[str] = None) -> None:
    """
    Ідемпотентна міграція схеми БД.
    Делегує в utils.db_migrate.migrate_if_needed(), щоб уникнути дублю і різних схем.
    """
    from utils.db_migrate import migrate_if_needed  # відкладений імпорт

    # використовуємо той самий шлях, що і основна міграція
    if db_path is None:
        db_path = os.getenv("DB_PATH") or os.path.join("storage", "bot.db")

    migrate_if_needed(db_path)

    # тихий режим за замовчуванням; вмикай лог за потреби
    if str(os.getenv("VERBOSE_MIGRATE", "0")).lower() in ("1", "true", "yes", "on"):
        log.info("[migrate] OK → %s", db_path)


if __name__ == "__main__":
    # дає можливість запускати з CLI:  python -m storage.migrate
    migrate()
