from __future__ import annotations
from .broker import Order, execute

def simulate(order: Order) -> dict:
    return execute(order)
