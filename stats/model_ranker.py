from __future__ import annotations

def rank_models(rows: list[dict]) -> list[dict]:
    """Проста агрегація: сортуємо за win_rate, далі за середнім RR."""
    # TODO: реальні метрики; зараз — ехо
    return sorted(rows, key=lambda r: (-r.get("win_rate", 0), -r.get("avg_rr", 0)))
