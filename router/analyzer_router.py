from __future__ import annotations
from typing import Optional
from core_config import CFG, ORRoute

_rr_idx = 0  # round-robin для HELP пулу

def pick_route(symbol: str) -> Optional[ORRoute]:
    global _rr_idx
    sym = symbol.upper().strip()

    # 1) по-монетний
    if sym in CFG.per_symbol:
        return CFG.per_symbol[sym]

    # 2) HELP пул (round-robin)
    if CFG.help_pool:
        route = CFG.help_pool[_rr_idx % len(CFG.help_pool)]
        _rr_idx += 1
        return route

    # 3) Fallback
    if CFG.fallback_enabled and CFG.fallback:
        return CFG.fallback
    return None
