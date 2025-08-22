from __future__ import annotations
from dataclasses import dataclass

@dataclass
class Order:
    symbol: str
    side: str   # BUY/SELL
    qty: float
    entry: float
    sl: float
    tp: float

def execute(order: Order) -> dict:
    """Заглушка paper‑trade: просто повертаємо підтвердження."""
    return {"status": "accepted", "order": order.__dict__}
