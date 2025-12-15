# app/services/telemetry_service.py
import time, json

from app.state.state_orchestrator import state_orchestrator

class TelemetryService:
    def __init__(self):
        self.latest = None
        self.history = []
        self.forward_hz = 10
        self.last_forward_ts = 0
        self.mqtt_client = None

    def set_mqtt_client(self, client):
        self.mqtt_client = client

    def update(self, data):
        now = time.time()

        # Store raw telemetry
        self.history.append(data)
        self.history = self.history[-2000:]

        # ---------------------------------------
        # APPLY STATE MACHINE + PROGRAM ENGINE
        # ---------------------------------------
        try:
            ms, ps = state_orchestrator.process(data)
        except Exception as e:
            print("[Telemetry] Orchestrator error:", e)
            return

       
        # ---------------------------------------
        # FORWARD TELEMETRY
        # ---------------------------------------
        self.latest = {
            "raw": data,
            "machine": ms.__dict__,
            "program": ps.serialize(),
        }

        if self.mqtt_client and (now - self.last_forward_ts >= 1 / self.forward_hz):
            self.mqtt_client.publish(
                "devices/edge1/telemetry",
                json.dumps(self.latest)
            )
            self.last_forward_ts = now


telemetry_service = TelemetryService()
