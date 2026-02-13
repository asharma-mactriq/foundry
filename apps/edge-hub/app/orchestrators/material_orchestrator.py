# app/orchestrators/material_orchestrator.py
import time
from app.state.material_state import material_state_manager

POT_CAPACITY_KG = 4.5
MIN_USABLE_VOLUME = 0.4   # kg — conservative

class MaterialOrchestrator:

    def process_telemetry(self, telemetry):
        ms = material_state_manager.state
        now = telemetry.get("ts", time.time())

        # -------------------------
        # PRESSURE
        # -------------------------
        if "pot_pressure" in telemetry:
            ms.pot_pressure = telemetry["pot_pressure"]

        

        # -------------------------
        # WEIGHT-BASED DISPENSE
        # -------------------------
        # if "pot_weight" in telemetry:
        #     prev = ms.current_pot_kg
        #     current = telemetry["pot_weight"]

        #     if prev == 0:
        #         ms.current_pot_kg = current
        #     else:
        #         delta = prev - current
        #         if delta > 0:
        #             ms.estimated_dispensed_kg += delta
        #             ms.current_pot_kg = current
        if "pot_weight" in telemetry:
            prev = ms.current_pot_kg
            current = telemetry["pot_weight"]

            if prev == 0:
                ms.current_pot_kg = current
            else:
                delta = current - prev

                # REFILL detected (weight increase)
                if delta > 0.05:   # 50g threshold
                    ms.current_pot_kg = current

                # DISPENSE detected (weight decrease)
                elif delta < -0.02:  # 20g noise filter
                    ms.estimated_dispensed_kg += abs(delta)
                    ms.current_pot_kg = current


        # -------------------------
        # DISPENSING STATE
        # -------------------------
        valves = telemetry.get("valves", {})
        ms.dispensing_active = bool(valves.get("dispense", 0))

        # -------------------------
        # CONFIDENCE
        # -------------------------
        if ms.current_pot_kg < MIN_USABLE_VOLUME:
            ms.paint_confidence = "LOW"
        else:
            ms.paint_confidence = "HIGH"

        ms.last_event_ts = now
        return ms


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
            ms.current_pot_kg = POT_CAPACITY_KG
            ms.last_event = event
            ms.last_event_ts = time.time()

        if event == "dispense_start":
            ms.dispensing_active = True
            ms.dispense_start_ts = time.time()
            ms.last_flow_ts = now


        if event == "dispense_stop":
            ms.dispensing_active = False
            ms.last_flow_ts = 0

        if event == "dispense_manual_done":
            ms.dispense_line_primed = True
            ms.last_event = event
            ms.last_event_ts = time.time()

material_orchestrator = MaterialOrchestrator()
