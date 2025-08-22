from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

@dataclass
class Outcome:
    uuid: str
    mfe: float
    mae: float
    progress: float
    status: str  # WIN|LOSE|NEUTRAL|PENDING

def resolve_outcome(ohlcv: list[dict], entry: float, sl: float, tp: float) -> Outcome:
    # TODO: обчислити MFE/MAE/Progress на основі свічок
    # Поки що — заглушка для hybrid
    return Outcome(uuid="", mfe=0.0, mae=0.0, progress=0.0, status="PENDING")
