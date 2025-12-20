# app/orchestrators/material_orchestrator.py
import time
from app.state.material_state import material_state_manager

POT_CAPACITY_ML = 4000   # set conservatively (NOT full extinguisher)
MIN_USABLE_VOLUME = 300   # ml — conservative
FLOW_TIMEOUT_S = 1.5

class MaterialOrchestrator:

    def process_telemetry(self, telemetry):
        ms = material_state_manager.state
        now = telemetry.get("ts", time.time())  # ✅ DEFINE NOW



        if "pressure" in telemetry:
            ms.pot_pressure = telemetry["pressure"]

        if "flow" in telemetry and ms.dispensing_active:
            if ms.last_flow_ts:
                dt = now - ms.last_flow_ts
                ms.estimated_dispensed_ml += telemetry["flow"] * dt
                ms.estimated_pot_volume_ml -= telemetry["flow"] * dt
            ms.last_flow_ts = now
            return ms
        
                # ---- Paint availability confidence ----
        if ms.dispensing_active:
            if ms.estimated_pot_volume_ml < MIN_USABLE_VOLUME:
                ms.paint_confidence = "LOW"
            else:
                ms.paint_confidence = "HIGH"

        # ---- Dispense health confidence ----
        if ms.dispensing_active:
            if now - ms.last_flow_ts > FLOW_TIMEOUT_S:
                ms.dispense_confidence = "LOW"
            else:
                ms.dispense_confidence = "HIGH"


    def on_workflow_event(self, event):
        ms = material_state_manager.state
        now = time.time()

        if event == "reprime_done":
            ms.dispense_line_primed = True
            ms.last_event = event
            ms.last_event_ts = time.time()

        if event == "refill_done":
            ms.pot_filled = True
            ms.pot_fill_ts = time.time()
            ms.estimated_pot_volume_ml = POT_CAPACITY_ML
            ms.last_event = event
            ms.last_event_ts = time.time()

        if event == "dispense_start":
            ms.dispensing_active = True
            ms.dispense_start_ts = time.time()
            ms.last_flow_ts = now


        if event == "dispense_stop":
            ms.dispensing_active = False
            ms.last_flow_ts = 0

material_orchestrator = MaterialOrchestrator()
