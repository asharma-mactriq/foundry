# app/services/device_state.py

import time
from app.modes.mode_manager import mode_manager
from app.modes.mode_types import PressureMode   # <-- FIXED IMPORT


class DeviceState:
    def __init__(self):
        self.online = False
        self.last_seen = 0
        self.last_ack = None
        self.last_telemetry = None

    def update_telemetry(self, data):
        """
        Telemetry drives:
        - pressure mode
        - vision mode (later when camera is integrated)
        """
        self.last_telemetry = data
        self.last_seen = time.time()
        self.online = True

        # Example: pressure rules
        pressure = data.get("pressure", None)
        if pressure is not None:
            if pressure < 0.8:
                mode_manager.set_pressure(PressureMode.low_pressure)
            elif pressure > 2.5:
                mode_manager.set_pressure(PressureMode.over_pressure)
            else:
                mode_manager.set_pressure(PressureMode.normal)

    def update_ack(self, ack):
        self.last_ack = ack
        self.last_seen = time.time()

    def get_status(self):
        age = time.time() - self.last_seen
        return {
            "online": age < 3,
            "last_seen_sec": age,
            "last_ack": self.last_ack,
            "last_telemetry": self.last_telemetry,
            "modes": mode_manager.get()
        }


device_state = DeviceState()
