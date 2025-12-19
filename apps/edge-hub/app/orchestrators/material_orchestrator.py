# app/orchestrators/material_orchestrator.py
import time
from app.state.material_state import material_state_manager

class MaterialOrchestrator:

    def process_telemetry(self, telemetry):
        ms = material_state_manager.state

        if "pressure" in telemetry:
            ms.pot_pressure = telemetry["pressure"]

        if "flow" in telemetry:
            if ms.dispensing_active:
                ms.estimated_dispensed_ml += telemetry["flow"] * 0.5  # 500ms tick

        return ms

    def on_workflow_event(self, event):
        ms = material_state_manager.state

        if event == "reprime_done":
            ms.dispense_line_primed = True
            ms.last_event = event
            ms.last_event_ts = time.time()

        if event == "refill_done":
            ms.pot_filled = True
            ms.pot_fill_ts = time.time()
            ms.last_event = event
            ms.last_event_ts = time.time()

        if event == "dispense_start":
            ms.dispensing_active = True
            ms.dispense_start_ts = time.time()

        if event == "dispense_stop":
            ms.dispensing_active = False

material_orchestrator = MaterialOrchestrator()
