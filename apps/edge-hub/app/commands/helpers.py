import time, uuid
from app.commands.command_queue import command_queue
from app.services.command_store import command_store

def create_and_queue_command(name, payload, device_id="1", priority=10, ttl_ms=3000):
    cmd_id = str(uuid.uuid4())
    now = time.time()
    cmd = {
        "cmd_id": cmd_id,
        "name": name,
        "deviceId": device_id,
        "type": "control",
        "payload": payload,
        "priority": priority,
        "issued_at": now,
        "valid_until": now + (ttl_ms / 1000),
        "status": "queued",
    }

    command_store.add(cmd)
    command_queue.push(cmd)
    return cmd_id
