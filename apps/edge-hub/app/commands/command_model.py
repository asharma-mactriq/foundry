from pydantic import BaseModel
import time
import uuid

class Command(BaseModel):
    cmd_id: str
    deviceId: str
    type: str
    payload: dict
    priority: int
    issued_at: float
    valid_until: float

def make_command(device_id: str, cmd_type: str, payload: dict, ttl_ms=500):
    now = time.time()
    return Command(
        cmd_id=str(uuid.uuid4()),
        deviceId=device_id,
        type=cmd_type,
        payload=payload,
        priority=10,
        issued_at=now,
        valid_until=now + (ttl_ms / 1000.0)
    )
