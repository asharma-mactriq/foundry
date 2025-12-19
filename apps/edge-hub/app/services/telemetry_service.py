# app/services/telemetry_service.py
import time, json
from types import SimpleNamespace

from app.orchestrators.state_orchestrator import state_orchestrator
from app.services.rule_engine import get_rule_engine

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
            print("[TELEMETRY] update() called with:", data)
            ms, ps = state_orchestrator.process(data)


        except Exception as e:
            print("[Telemetry] Orchestrator error:", e)
            return

# ---------------------------------------
        # 🔥 RUN RULE ENGINE (THIS WAS MISSING)
        # ---------------------------------------
        try:
            print("[TELEMETRY] invoking rule engine")
            rule_engine = get_rule_engine(mqtt_client=self.mqtt_client)

            fired = rule_engine.evaluate_all(
                raw=data,
                machine=SimpleNamespace(**ms.__dict__),
                program=SimpleNamespace(**ps.serialize())
            )
            if fired:
                print("[RULES] Fired:", fired)
        except Exception as e:
            print("[Telemetry] Rule engine error:", e)



       
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
