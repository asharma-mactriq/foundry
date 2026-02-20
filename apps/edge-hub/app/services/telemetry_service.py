# app/services/telemetry_service.py
import time, json
from types import SimpleNamespace
from app.core.telemetry_validator import TelemetryValidator
from app.orchestrators.state_orchestrator import state_orchestrator
from app.services.rule_engine import get_rule_engine
from app.state.material_state import material_state_manager
from app.program.program_engine import program_engine
from app.core import clock

class TelemetryService:
    def __init__(self):
        self.latest = None
        self.history = []
        self.forward_hz = 10
        self.last_forward_ts = 0
        self.mqtt_client = None
        self.last_program_event_ts = 0
        self.validator = TelemetryValidator()
        self.last_valid = {}


    def set_mqtt_client(self, client):
        self.mqtt_client = client

    def update(self, data):
        now = clock.mono()
        print("SOURCE TS:", data.get("ts"), "EDGE TS:", data.get("ts_edge"))

        clean = self.validator.sanitize(data, self.last_valid)
        # self.last_valid = clean

        # clean = self.validator.sanitize(data, self.last_valid)

        # Only update last_valid when weight is valid
        if clean.get("pot_weight_valid", 1):
            self.last_valid = clean
        else:
            # If invalid, preserve last known good weight
            clean["pot_weight"] = self.last_valid.get("pot_weight", 0.0)


        # Store raw telemetry
        self.history.append(clean)
        self.history = self.history[-2000:]

        # ---------------------------------------
        # APPLY STATE MACHINE + PROGRAM ENGINE
        # ---------------------------------------
        try:
            print("[TELEMETRY] update() called with:", clean)
            ms, ps = state_orchestrator.process(clean)

            # from app.orchestrators.startup_orchestrator import startup_orchestrator
            # startup_orchestrator.process()

            # if program_engine and ps.last_event_ts:
            #     if ps.last_event_ts != self.last_program_event_ts:
            #         program_engine.on_event(ms, ps)
            #         self.last_program_event_ts = ps.last_event_ts
            if program_engine:
                program_engine.on_event(ms, ps)



        except Exception as e:
            print("[Telemetry] Orchestrator error:", e)
            return

# ---------------------------------------
        # 🔥 RUN RULE ENGINE (THIS WAS MISSING)
        # # ---------------------------------------
        # try:
        #     print("[TELEMETRY] invoking rule engine")
        #     rule_engine = get_rule_engine(mqtt_client=self.mqtt_client)

        #     fired = rule_engine.evaluate_all(
        #         raw=data,
        #         machine=SimpleNamespace(**ms.__dict__),
        #         program=SimpleNamespace(**ps.serialize()),
        #         material=SimpleNamespace(**material_state_manager.state.__dict__)
        #     )
        #     if fired:
        #         print("[RULES] Fired:", fired)
        # except Exception as e:
        #     print("[Telemetry] Rule engine error:", e)



       
        # ---------------------------------------
        # FORWARD TELEMETRY
        # ---------------------------------------
        self.latest = {
            "raw": data,
            "clean": clean,     # this is what logic used
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
