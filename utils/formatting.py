from __future__ import annotations
from datetime import datetime
from zoneinfo import ZoneInfo
from core_config import CFG
import os

def now_stamp() -> str:
    tz = ZoneInfo(CFG.tz_name)
    return datetime.now(tz).strftime("%Y-%m-%d_%H-%M-%S")

def save_report(symbol: str, markdown_lines: list[str]) -> str:
    os.makedirs("storage/reports", exist_ok=True)
    name = f"{now_stamp()}__{symbol}.md"
    path = os.path.join("storage/reports", name)
    with open(path, "w", encoding="utf-8") as f:
        if isinstance(markdown_lines, (list, tuple)):
            f.write("\n".join(markdown_lines).strip() + "\n")
        else:
            f.write(str(markdown_lines).strip() + "\n")
    return path
