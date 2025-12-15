import time, uuid, json
from app.commands.command_registry import command_registry
from app.services.command_store import command_store
from app.commands.command_queue import command_queue
from app.modes.mode_manager import mode_manager
from app.services.device_state import device_state

class CommandDispatcher:
    def __init__(self, mqtt_client):
        self.mqtt_client = mqtt_client

    def dispatch(self, name: str, payload: dict):
        spec = command_registry.get(name)
        if not spec:
            raise ValueError(f"Unknown command: {name}")

        mode_state = mode_manager.get()
        if not spec.is_allowed_in_mode(mode_state):
            raise ValueError(f"Command {name} not allowed in mode {mode_state['operation']} / process {mode_state['process']}")

        ok, reason = spec.check_preconditions(device_state)
        if not ok:
            raise ValueError(f"Precondition failed: {reason}")

        cmd = {
            "cmd_id": str(uuid.uuid4()),
            "deviceId": "edge1",
            "type": name,   # <-- FIX
            "name": name,
            "group": spec.group,
            "payload": payload,
            "issued_at": time.time(),
            "valid_until": time.time() + spec.timeout_ms/1000.0,
            "priority": spec.priority,
            "status": "queued"
        }

        command_store.add(cmd)
        command_queue.push(cmd)
        return cmd

dispatcher = None   # set in main on startup
