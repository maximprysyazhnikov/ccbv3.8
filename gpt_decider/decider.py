from __future__ import annotations
import re
from typing import TypedDict

class Decision(TypedDict):
    push: bool
    direction: str | None
    confidence: int | None
    reason: str

CONF_THRESHOLD = 75  # можна винести в ENV

def decide_from_markdown(lines: list[str]) -> Decision:
    txt = "\n".join(lines)
    dir_m = re.search(r"\b(LONG|SHORT|NO_TRADE)\b", txt, re.I)
    conf_m = re.search(r"Confidence[^0-9]*(\d{1,3})\%", txt, re.I)

    direction = dir_m.group(1).upper() if dir_m else None
    confidence = int(conf_m.group(1)) if conf_m else None

    if direction in ("LONG", "SHORT") and (confidence or 0) >= CONF_THRESHOLD:
        return {"push": True, "direction": direction, "confidence": confidence, "reason": "Signal strong enough"}
    return {"push": False, "direction": direction, "confidence": confidence, "reason": "Weak or no trade"}
