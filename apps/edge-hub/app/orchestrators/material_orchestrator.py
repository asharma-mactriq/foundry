# app/orchestrators/material_orchestrator.py

import time
from app.state.material_state import material_state_manager
from app.state.program_state import program_state, ProgramPhase   # needed for pot_weight_absolute fill check

POT_CAPACITY_KG = 4.5
MIN_USABLE_VOLUME = 0.4   # kg — fallback if pot_min_kg not in telemetry


class MaterialOrchestrator:

    def process_telemetry(self, telemetry: dict):
        ms = material_state_manager.state
        now = telemetry.get("ts", time.time())

        # ── Pressure ──────────────────────────────────────────────
        if "pot_pressure" in telemetry:
            ms.pot_pressure = float(telemetry["pot_pressure"])

        # ── Threshold config from firmware ────────────────────────
        if "pot_min_kg" in telemetry:
            ms.pot_min_kg = float(telemetry["pot_min_kg"])

        if "res_min_kg" in telemetry:
            ms.res_min_kg = float(telemetry["res_min_kg"])

        # ── Reservoir weight — soft hint only ─────────────────────
        if "reservoir_weight" in telemetry:
            ms.reservoir_weight_raw = float(telemetry["reservoir_weight"])
        ms.reservoir_weight_valid = bool(telemetry.get("res_weight_valid", 0))

        # ── Pot weight absolute — primary reliable signal ─────────
        # Firmware sends pot_weight_absolute as the real load cell reading.
        # Use this as source of truth. pot_weight (relative) is ignored
        # when pot_weight_absolute is present.
        if "pot_weight_absolute" in telemetry:
            raw = telemetry["pot_weight_absolute"]

            if raw is not None:
                prev = ms.current_pot_kg
                current = float(raw)
                filling = program_state.phase == ProgramPhase.POT_FILLING

                if prev is None:
                    # First valid reading — accept unconditionally.
                    # This is why current_pot_kg defaults to None, not 0.0:
                    # 0.0 would be caught by the delta filter and silently dropped.
                    ms.current_pot_kg = current
                    ms.estimated_dispensed_kg = 0.0
                    print(f"[MATERIAL_ORCH] First weight reading: {current:.3f}kg")
                else:
                    delta = current - prev

                    if filling:
                        # During fill, accept small upward increments.
                        # Thick paste fills slowly — 0.005kg threshold
                        # captures real fill progress without noise.
                        # Downward spikes during fill = sensor glitch, ignore.
                        if delta > 0.005:
                            ms.current_pot_kg = current
                    else:
                        # Normal operation:
                        # 50g+ increase = refill event
                        # 20g+ decrease = dispense event
                        # Smaller deltas = noise, ignore
                        if delta > 0.05:
                            ms.current_pot_kg = current
                        elif delta < -0.02:
                            ms.estimated_dispensed_kg += abs(delta)
                            ms.current_pot_kg = current

        elif "pot_weight" in telemetry:
            # Fallback: firmware sending relative weight only.
            # Less reliable — use only if pot_weight_absolute not present.
            raw = telemetry["pot_weight"]
            if raw is not None:
                prev = ms.current_pot_kg
                current = float(raw)

                if prev is None:
                    ms.current_pot_kg = current
                    ms.estimated_dispensed_kg = 0.0
                else:
                    delta = current - prev
                    if delta > 0.05:
                        ms.current_pot_kg = current
                    elif delta < -0.02:
                        ms.estimated_dispensed_kg += abs(delta)
                        ms.current_pot_kg = current

        # ── Dispense valve state ──────────────────────────────────
        valves = telemetry.get("valves", {})
        ms.dispensing_active = bool(valves.get("dispense", 0))

        # ── Paint confidence ──────────────────────────────────────
        if ms.current_pot_kg is None:
            ms.paint_confidence = "UNKNOWN"
        else:
            threshold = ms.pot_min_kg if ms.pot_min_kg > 0 else MIN_USABLE_VOLUME
            ms.paint_confidence = "LOW" if ms.current_pot_kg < threshold else "HIGH"

        # NOTE: consecutive_failed_refills is written directly by
        # mid_refill_orchestrator.process() after each refill outcome.
        # No sync needed here — it lives on MaterialState.

        ms.last_event_ts = now
        return ms

    def on_workflow_event(self, event: str):
        """Called from command_executor on firmware workflow events."""
        ms = material_state_manager.state
        now = time.time()

        if event == "pot_fill_stopped":
            ms.pot_filled = True
            ms.last_event = event
            ms.last_event_ts = now

        elif event == "line_prime_stopped":
            ms.line_primed = True
            ms.last_event = event
            ms.last_event_ts = now

        elif event == "dispense_complete":
            ms.dispensing_active = False
            ms.last_flow_ts = now
            ms.last_event = event
            ms.last_event_ts = now

        elif event == "dispense_stopped":
            ms.dispensing_active = False
            ms.last_event = event
            ms.last_event_ts = now


material_orchestrator = MaterialOrchestrator()

# # app/orchestrators/material_orchestrator.py

# import time
# from app.state.material_state import material_state_manager

# POT_CAPACITY_KG = 4.5
# MIN_USABLE_VOLUME = 0.4   # kg — fallback if pot_min_kg not in telemetry


# class MaterialOrchestrator:

#     def process_telemetry(self, telemetry):
#         ms = material_state_manager.state
#         now = telemetry.get("ts", time.time())

#         # ── Pressure ──────────────────────────────────────────────
#         if "pot_pressure" in telemetry:
#             ms.pot_pressure = telemetry["pot_pressure"]

#         # ── Threshold config from firmware ────────────────────────
#         if "pot_min_kg" in telemetry:
#             ms.pot_min_kg = telemetry["pot_min_kg"]

#         if "res_min_kg" in telemetry:
#             ms.res_min_kg = telemetry["res_min_kg"]

#         # ── Reservoir weight — soft hint only ─────────────────────
#         if "reservoir_weight" in telemetry:
#             ms.reservoir_weight_raw = telemetry["reservoir_weight"]
#         ms.reservoir_weight_valid = bool(telemetry.get("res_weight_valid", 0))

#         # ── Pot weight — primary reliable signal ──────────────────
#         if "pot_weight" in telemetry:
#             prev = ms.current_pot_kg
#             current = float(telemetry["pot_weight"])

#             if prev == 0:
#                 ms.current_pot_kg = current
#                 ms.estimated_dispensed_kg = 0.0
#             else:
#                 delta = current - prev
#                 if delta > 0.05:       # 50g+ increase = refill/fill event
#                     ms.current_pot_kg = current
#                 elif delta < -0.02:    # 20g+ decrease = dispense event
#                     ms.estimated_dispensed_kg += abs(delta)
#                     ms.current_pot_kg = current

#         if "pot_weight_absolute" in telemetry:
#             raw = telemetry["pot_weight_absolute"]
#             if raw is None:
#                 pass  # no reading yet — leave current_pot_kg unchanged
#             else:
#                 prev = ms.current_pot_kg
#                 current = float(raw)
#                 filling = program_state.phase == ProgramPhase.POT_FILLING

#                 if prev is None:
#                     # First valid reading — accept unconditionally
#                     ms.current_pot_kg = current
#                     ms.estimated_dispensed_kg = 0.0
#                 else:
#                     delta = current - prev
#                     if filling:
#                         if delta > 0.005:
#                             ms.current_pot_kg = current
#                         # large drops during fill are sensor glitch — ignore
#                     else:
#                         if delta > 0.05:
#                             ms.current_pot_kg = current
#                         elif delta < -0.02:
#                             ms.estimated_dispensed_kg += abs(delta)
#                             ms.current_pot_kg = current

#         # ── Dispense valve state ──────────────────────────────────
#         valves = telemetry.get("valves", {})
#         ms.dispensing_active = bool(valves.get("dispense", 0))

#         # ── Paint confidence ──────────────────────────────────────
#         threshold = ms.pot_min_kg if ms.pot_min_kg > 0 else MIN_USABLE_VOLUME
#         ms.paint_confidence = "LOW" if ms.current_pot_kg < threshold else "HIGH"

#         # ── Sync consecutive_failed_refills from program_engine ───
#         # Rules engine reads material_state, but refill outcomes are tracked
#         # in program_engine. Sync here so rules can see it.
#         try:
#             from app.program.program_engine import program_engine
#             if program_engine is not None:
#                 ms.consecutive_failed_refills = program_engine.consecutive_failed_refills
#         except Exception:
#             pass

#         ms.last_event_ts = now
#         return ms

#     def on_workflow_event(self, event: str):
#         """Called from command_executor on firmware workflow events."""
#         ms = material_state_manager.state
#         now = time.time()

#         if event == "pot_fill_stopped":
#             ms.pot_filled = True
#             ms.last_event = event
#             ms.last_event_ts = now

#         elif event == "line_prime_stopped":
#             ms.line_primed = True
#             ms.last_event = event
#             ms.last_event_ts = now

#         elif event == "dispense_complete":
#             ms.dispensing_active = False
#             ms.last_flow_ts = now
#             ms.last_event = event
#             ms.last_event_ts = now

#         elif event == "dispense_stopped":
#             ms.dispensing_active = False
#             ms.last_event = event
#             ms.last_event_ts = now


# material_orchestrator = MaterialOrchestrator()

# # app/orchestrators/material_orchestrator.py
# import time
# from app.state.material_state import material_state_manager

# POT_CAPACITY_KG = 4.5
# MIN_USABLE_VOLUME = 0.4   # kg — conservative

# class MaterialOrchestrator:

#     def process_telemetry(self, telemetry):
#         ms = material_state_manager.state
#         now = telemetry.get("ts", time.time())

#         # -------------------------
#         # PRESSURE
#         # -------------------------
#         if "pot_pressure" in telemetry:
#             ms.pot_pressure = telemetry["pot_pressure"]

#         if "pot_min_kg" in telemetry:
#             ms.pot_min_kg = telemetry["pot_min_kg"]

#         if "res_min_kg" in telemetry:
#             ms.res_min_kg = telemetry["res_min_kg"]


        

#         # -------------------------
#         # WEIGHT-BASED DISPENSE
#         # -------------------------
#         # if "pot_weight" in telemetry:
#         #     prev = ms.current_pot_kg
#         #     current = telemetry["pot_weight"]

#         #     if prev == 0:
#         #         ms.current_pot_kg = current
#         #     else:
#         #         delta = prev - current
#         #         if delta > 0:
#         #             ms.estimated_dispensed_kg += delta
#         #             ms.current_pot_kg = current
#         if "pot_weight" in telemetry:
#             prev = ms.current_pot_kg
#             current = telemetry["pot_weight"]

#             if prev == 0:
#                 ms.current_pot_kg = current
#                 ms.estimated_dispensed_kg = 0.0

#             else:
#                 delta = current - prev

#                 # REFILL detected (weight increase)
#                 if delta > 0.05:   # 50g threshold
#                     ms.current_pot_kg = current

#                 # DISPENSE detected (weight decrease)
#                 elif delta < -0.02:  # 20g noise filter
#                     ms.estimated_dispensed_kg += abs(delta)
#                     ms.current_pot_kg = current


#         # -------------------------
#         # DISPENSING STATE
#         # -------------------------
#         valves = telemetry.get("valves", {})
#         ms.dispensing_active = bool(valves.get("dispense", 0))

#         # -------------------------
#         # CONFIDENCE
#         # -------------------------
#         threshold = ms.pot_min_kg if ms.pot_min_kg > 0 else MIN_USABLE_VOLUME

#         if ms.current_pot_kg < threshold:
#             ms.paint_confidence = "LOW"
#         else:
#             ms.paint_confidence = "HIGH"

#         # if ms.current_pot_kg < MIN_USABLE_VOLUME:
#         #     ms.paint_confidence = "LOW"
#         # else:
#         #     ms.paint_confidence = "HIGH"

#         ms.last_event_ts = now
#         return ms


#     def on_workflow_event(self, event):
#         ms = material_state_manager.state
#         now = time.time()

#         if event == "reprime_done":
#             ms.dispense_line_primed = True
#             ms.last_event = event
#             ms.last_event_ts = now

#         if event == "refill_done":
#             ms.pot_filled = True
#             ms.pot_fill_ts = now
#             ms.current_pot_kg = POT_CAPACITY_KG
#             ms.last_event = event
#             ms.last_event_ts = now

#         if event == "dispense_start":
#             ms.dispensing_active = True
#             ms.dispense_start_ts = now
#             ms.last_flow_ts = now
#             ms.last_event = event
#             ms.last_event_ts = now

#         if event == "dispense_stop":
#             ms.dispensing_active = False
#             ms.last_flow_ts = 0
#             ms.last_event = event
#             ms.last_event_ts = now

#         if event == "dispense_manual_done":
#             ms.dispense_line_primed = True
#             ms.last_event = event
#             ms.last_event_ts = now

# material_orchestrator = MaterialOrchestrator()
