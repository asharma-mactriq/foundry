from enum import Enum
import time

class SystemPhase(str, Enum):
    BOOTING = "booting"
    INIT = "init"
    READY = "ready"
    FAULT = "fault"

class SystemState:
    def __init__(self):
        self.phase = SystemPhase.BOOTING
        self.last_event = None
        self.last_event_ts = time.time()

    def set_phase(self, phase: SystemPhase, reason: str = None):
        self.phase = phase
        self.last_event = reason
        self.last_event_ts = time.time()
        print(f"[SYSTEM] phase → {phase} ({reason})")

system_state = SystemState()
