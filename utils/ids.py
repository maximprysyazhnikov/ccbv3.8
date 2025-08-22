from __future__ import annotations
import uuid, time

def new_uuid() -> str:
    return str(uuid.uuid4())

def ts_ms() -> int:
    return int(time.time() * 1000)
