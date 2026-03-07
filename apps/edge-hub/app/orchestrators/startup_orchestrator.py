# app/orchestrators/startup_orchestrator.py

import json
import time
from app.state.program_state import program_state, ProgramPhase
from app.state.material_state import material_state_manager
from app.state.machine_state import machine_state_manager
from app.config.paint_profile import PaintProfile, DEFAULT_PROFILE

# from app.services.command_executor import executor


class StartupOrchestrator:
    """
    Drives the startup sequence:
        STARTUP → POT_FILLING → PRESSURISING → LINE_PRIMING → READY

    All timing comes from the PaintProfile injected at begin().
    Call reset() + begin(profile) at the start of every new program.
    """

    def __init__(self):
        self.profile: PaintProfile = DEFAULT_PROFILE
        # self.TEST_MODE = False   # ← Actual 
        self.executor = None
        self.TEST_MODE = True   # ← Test 
        self._reset_state()


    def _reset_state(self):
        # Fill phase
        self._fill_cmd_sent = False
        self._fill_stop_sent = False
        self._fill_phase_start_ts = 0.0
        self._fill_phase_start_weight = 0.0
        self._fill_last_weight = 0.0
        self._fill_last_weight_ts = 0.0
        self._settle_start_ts = 0.0
        self._fill_state = "IDLE"
        self._active_cmd = None

        # Pressurise phase
        self._pressurise_cmd_sent = False
        self._pressurise_start_ts = 0.0

        # Line prime phase
        self._prime_cmd_sent = False
        self._prime_stop_sent = False

        self._prime_start_ts = 0.0
        self._prime_start_weight = 0.0
        self._rate_window_start_ts = 0.0
        self._rate_window_start_weight = 0.0
        self._peak_drop_rate = 0.0
        self._nozzle_crack_ts = 0.0
        self._nozzle_cracked = False

    def reset(self):
        """Call at program start to wipe all one-shot flags."""
        self._reset_state()
        print("[STARTUP_ORCH] Reset")



    def begin(self, profile: PaintProfile = None):
        """
        Called once when startup.sequence ACK completes.
        Transitions STARTUP → POT_FILLING and sets the profile for this run.
        """
        if profile:
            self.profile = profile

        mat = material_state_manager.state
        now = time.time()

        # Ignore invalid weight
        # if mat.current_pot_kg <= 0:
        #     return

        # current_kg = mat.current_pot_kg or 0.0

        current_kg = mat.current_pot_kg or 0.0
        target_kg = self.profile.pot_fill_target_kg

        # ─────────────────────────────────────────
        # 1️⃣ Skip fill if already above target
        # ─────────────────────────────────────────
        if current_kg >= target_kg:

            from app.commands.helpers import create_and_queue_command

            print(
                f"[STARTUP_ORCH] Pot already above target "
                f"({current_kg:.3f}kg >= {target_kg}kg) — skipping fill"
            )    
            create_and_queue_command(name="pot.fill_stop", payload={})
            # create_and_queue_command(name="pot.fill_stop", payload={})
            program_state.begin_pot_filling()   # enter POT_FILLING first
            self._fill_state = "DEPRESSURISE_POT"
            program_state.on_pot_filled()   # → PRESSURISING
            return


        # if mat.current_pot_kg >= self.profile.pot_fill_target_kg:
        #     print("[STARTUP_ORCH] Pot already above target — skipping fill")
        #     program_state.on_pot_filled()
        #     return
        


        self._fill_phase_start_ts = now
        self._fill_phase_start_weight = current_kg
        self._fill_last_weight = current_kg
        self._fill_last_weight_ts = now
        self._fill_cmd_sent = False
        self._fill_stop_sent = False

        program_state.begin_pot_filling()

        self._fill_state = "DEPRESSURISE_POT"

        if self.TEST_MODE:
            print("[STARTUP_ORCH] TEST MODE ENABLED — bypassing sensors")
            
        print(
            f"[STARTUP_ORCH] begin() — profile={self.profile.name} "
            f"pot_now={current_kg:.3f}kg "
            f"target={target_kg}kg"
        )

    # ──────────────────────────────────────────────────────────────
    # Called every telemetry tick from state_orchestrator
    # ──────────────────────────────────────────────────────────────
    def process(self):
        ps = program_state
        mat = material_state_manager.state
        ms = machine_state_manager.state

        if ps.phase == ProgramPhase.POT_FILLING:
            self._handle_pot_filling(mat)
        elif ps.phase == ProgramPhase.PRESSURISING:
            self._handle_pressurising(ms)
        elif ps.phase == ProgramPhase.LINE_PRIMING:
            self._handle_line_priming(mat)

    # ──────────────────────────────────────────────────────────────
    # PHASE 1: POT FILLING
    # Primary signal: pot_weight rising
    # ──────────────────────────────────────────────────────────────
#     def _handle_pot_filling(self, mat):
#         weight_valid = mat.current_pot_kg is not None and mat.current_pot_kg > 0

#         from app.commands.helpers import create_and_queue_command
#         p = self.profile
#         now = time.time()

#         current_kg = mat.current_pot_kg or 0.0

#         print("DEBUG POT_FILLING tick", mat.current_pot_kg)

#         if not self._fill_cmd_sent:
#             print(f"[STARTUP_ORCH] Opening paint_inlet — target={p.pot_fill_target_kg}kg")
#             create_and_queue_command(
#                 name="pot.fill_start",
#                 payload={"target_kg": p.pot_fill_target_kg}
#             )
#             self._fill_cmd_sent = True
#             self._fill_phase_start_ts = now
#             self._fill_phase_start_weight = current_kg
#             self._fill_last_weight = current_kg
#             self._fill_last_weight_ts = now
#             return

#         # ── Step 2: Already sent fill_stop — wait for weight to settle ──
#         if self._fill_stop_sent:
#             settle_elapsed = now - self._settle_start_ts
#             if settle_elapsed >= p.pot_fill_settle_s:
#                 print(
#                     f"[STARTUP_ORCH] Pot fill settle done ({settle_elapsed:.1f}s) "
#                     f"final={current_kg:.3f}kg → pressurising"
#                 )
#                 program_state.on_pot_filled()  # → PRESSURISING
#                 self._pressurise_start_ts = now
#             return

#         # ── Track weight change over time ──
#         weight_gained_total = current_kg - self._fill_phase_start_weight
#         elapsed_total = now - self._fill_phase_start_ts

#         # Update last-seen weight tracker
#         if current_kg != self._fill_last_weight:
#             self._fill_last_weight = current_kg
#             self._fill_last_weight_ts = now

#         time_since_last_change = now - self._fill_last_weight_ts

#         # ── Early flow-start check: if weight hasn't moved at all ──
#         elapsed_since_start = now - self._fill_phase_start_ts
#         # if elapsed_since_start > p.pot_fill_flow_start_timeout_s:
#         #     if weight_gained_total < p.pot_fill_min_gain_kg:
#         #         print(
#         #             f"[STARTUP_ORCH] ABORT: Pot fill — no flow detected after "
#         #             f"{elapsed_since_start:.0f}s (gained {weight_gained_total:.3f}kg)"
#         #         )
#         #         create_and_queue_command(name="pot.fill_stop", payload={})
#         #         program_state.abort("pot_fill_no_flow")
#         #         return

#         if not weight_valid:
#             if not self._fill_stop_sent and elapsed_since_start >= p.pot_fill_open_time_s:
#                 print("[STARTUP_ORCH] Weight invalid — closing inlet (time-based)")
#                 create_and_queue_command(name="pot.fill_stop", payload={})
#                 self._fill_stop_sent = True
#                 self._settle_start_ts = now
#             return

#         # ── Total timeout with progressive extension ──
#         # if elapsed_since_start > p.pot_fill_total_timeout_s:
#         #     if time_since_last_change > 10.0:
#         #         # Weight stopped moving — assume blocked or reservoir empty
#         #         print(
#         #             f"[STARTUP_ORCH] ABORT: Pot fill stalled — "
#         #             f"no weight change for {time_since_last_change:.0f}s"
#         #         )
#         #         create_and_queue_command(name="pot.fill_stop", payload={})
#         #         program_state.abort("pot_fill_stalled")
#         #         return
            
# # // TESTING
#         if elapsed_since_start > p.pot_fill_total_timeout_s:
#             if time_since_last_change > 10.0:
#                 print(
#                     f"[STARTUP_ORCH] WARNING: Pot fill stalled — forcing continue"
#                 )

#                 # close inlet and proceed anyway
#                 create_and_queue_command(name="pot.fill_stop", payload={})

#                 self._fill_stop_sent = True
#                 self._settle_start_ts = now
#                 return

#             # Weight still moving but slowly — log and continue
#             print(
#                 f"[STARTUP_ORCH] Pot fill slow — {current_kg:.3f}kg "
#                 f"(+{weight_gained_total:.3f}kg in {elapsed_since_start:.0f}s)"
#             )

#         # ── Target reached ──
#         if current_kg >= p.pot_fill_target_kg:
#             print(
#                 f"[STARTUP_ORCH] Pot filled ({current_kg:.3f}kg) — "
#                 f"closing inlet, settling {p.pot_fill_settle_s}s"
#             )
#             create_and_queue_command(name="pot.fill_stop", payload={})
#             self._fill_stop_sent = True
#             self._settle_start_ts = now
#             return

#         # ── Progress log every 5s ──
#         if int(elapsed_since_start) % 5 == 0 and int(elapsed_since_start) > 0:
#             print(
#                 f"[STARTUP_ORCH] Filling: {current_kg:.3f}kg / {p.pot_fill_target_kg}kg "
#                 f"(+{weight_gained_total:.3f}kg in {elapsed_since_start:.0f}s)"
#             )

    def _handle_pot_filling(self, mat):

        from app.commands.helpers import create_and_queue_command

        p = self.profile
        now = time.time()
        current_kg = mat.current_pot_kg or 0.0

        # 1️⃣ Depressurise pot
        if self._fill_state == "DEPRESSURISE_POT":

            if not self._active_cmd:

                print("[STARTUP_ORCH] Venting pot")

                self._active_cmd = create_and_queue_command(
                    name="pot.depressurise",
                    payload={}
                )
                return

            if self.executor.is_completed(self._active_cmd):

                self._active_cmd = None
                self._fill_state = "PRESSURISE_RES"

        # 2️⃣ Pressurise reservoir
        if self._fill_state == "PRESSURISE_RES":

            if not self._active_cmd:

                print("[STARTUP_ORCH] Pressurising reservoir")

                self._active_cmd = create_and_queue_command(
                    name="res.pressurise",
                    payload={"open_ms": int(p.pressurise_open_s * 1000)}
                )
                return

            if self.executor.is_completed(self._active_cmd):

                self._active_cmd = None
                self._fill_state = "OPEN_INLET"


        # 3️⃣ Open inlet
        if self._fill_state == "OPEN_INLET":

            if not self._active_cmd:

                print("[STARTUP_ORCH] Opening inlet")

                self._active_cmd = create_and_queue_command(
                    name="pot.fill_start",
                    payload={"target_kg": p.pot_fill_target_kg}
                )
                return

            if self.executor.is_completed(self._active_cmd):

                self._active_cmd = None
                self._fill_state = "OPEN_VENT"


        # 4️⃣ Open vent
        if self._fill_state == "OPEN_VENT":

            if not self._active_cmd:

                print("[STARTUP_ORCH] Opening pot vent")

                self._active_cmd = create_and_queue_command(
                    name="pot.vent_open",
                    payload={}
                )
                return

            if self.executor.is_completed(self._active_cmd):

                self._active_cmd = None
                self._fill_phase_start_ts = now
                self._fill_phase_start_weight = current_kg
                self._fill_state = "FILLING"

        # 5️⃣ Filling
        if self._fill_state == "FILLING":

            gained = current_kg - self._fill_phase_start_weight
            elapsed = now - self._fill_phase_start_ts

            print(
                f"[STARTUP_ORCH] Filling pot {current_kg:.3f}kg "
                f"(+{gained:.3f}kg)"
            )

            # TEST MODE: ignore weight
            if self.TEST_MODE:
                if elapsed > 3:
                    print("[STARTUP_ORCH] TEST MODE forcing fill completion")
                    self._fill_state = "CLOSE_INLET"
                return

            if current_kg >= p.pot_fill_target_kg:
                print("[STARTUP_ORCH] Target reached")
                self._fill_state = "CLOSE_INLET"
                return

            if elapsed > p.pot_fill_total_timeout_s:
                print("[STARTUP_ORCH] Fill timeout")
                self._fill_state = "CLOSE_INLET"
                return

            return


        # 6️⃣ Close inlet
        if self._fill_state == "CLOSE_INLET":

            if not self._active_cmd:

                print("[STARTUP_ORCH] Closing inlet")

                self._active_cmd = create_and_queue_command(
                    name="pot.fill_stop",
                    payload={}
                )
                return

            if self.executor.is_completed(self._active_cmd):

                self._active_cmd = None
                self._fill_state = "CLOSE_VENT"

        # 7️⃣ Close vent
        if self._fill_state == "CLOSE_VENT":

            if not self._active_cmd:

                print("[STARTUP_ORCH] Closing pot vent")

                self._active_cmd = create_and_queue_command(
                    name="pot.vent_close",
                    payload={}
                )
                return

            if self.executor.is_completed(self._active_cmd):

                self._active_cmd = None
                self._settle_start_ts = now
                self._fill_state = "SETTLING"


        # 8️⃣ Settling
        if self._fill_state == "SETTLING":

            if now - self._settle_start_ts < p.pot_fill_settle_s:
                return

            print("[STARTUP_ORCH] Pot fill settled")

            self._fill_state = "DEPRESSURISE_RES"
            return


        # 9️⃣ Depressurise reservoir
        if self._fill_state == "DEPRESSURISE_RES":

            if not self._active_cmd:

                self._active_cmd = create_and_queue_command(
                    name="res.depressurise",
                    payload={}
                )
                return

            if self.executor.is_completed(self._active_cmd):

                self._active_cmd = None
                self._fill_state = "COMPLETE"

        # 🔟 Complete
        if self._fill_state == "COMPLETE":

            print("[STARTUP_ORCH] Fill complete → PRESSURISING")

            program_state.on_pot_filled()

            self._fill_state = "DONE"

    # ──────────────────────────────────────────────────────────────
    # PHASE 2: PRESSURISATION
    # Time-based primary. Pressure sensor = safety guard only.
    # ──────────────────────────────────────────────────────────────
    def _handle_pressurising(self, ms):
        from app.commands.helpers import create_and_queue_command
        p = self.profile
        now = time.time()

        # ── Send pressurise command once ──
        if not self._pressurise_cmd_sent:
            open_ms = int(p.pressurise_open_s * 1000)
            print(
                f"[STARTUP_ORCH] Pressurising pot — "
                f"open_ms={open_ms} profile={p.name}"
            )
            create_and_queue_command(
                name="pot.pressurise",
                payload={"open_ms": open_ms}
            )
            self._pressurise_cmd_sent = True
            self._pressurise_start_ts = now
            return

        elapsed = now - self._pressurise_start_ts
        pressure = ms.pressure   # may be unreliable — used for safety only

        # ── Safety: overpressure guard ──
        # if pressure >= p.pressurise_safety_bar:
        #     print(
        #         f"[STARTUP_ORCH] ABORT: Overpressure detected "
        #         f"({pressure:.2f} bar >= {p.pressurise_safety_bar} bar)"
        #     )
        #     create_and_queue_command(name="pot.depressurise", payload={})
        #     program_state.abort("overpressure")
        #     return

        if pressure >= p.pressurise_safety_bar:
            print(
                f"[STARTUP_ORCH] WARNING: Overpressure detected "
                f"({pressure:.2f} bar) — ignoring in test mode"
            )

        # ── Hard max time ceiling ──
        if elapsed >= p.pressurise_max_open_s:
            print(
                f"[STARTUP_ORCH] Pressurise max time reached ({elapsed:.1f}s) — proceeding"
            )
            self._complete_pressurisation()
            return

        if self.TEST_MODE:
            if elapsed > 2:
                print("[STARTUP_ORCH] TEST MODE forcing pressurise complete")
                self._complete_pressurisation()
            return

        # ── Primary: nominal open time elapsed ──
        if elapsed >= p.pressurise_open_s:
            print(
                f"[STARTUP_ORCH] Pressurise nominal time done ({elapsed:.1f}s) "
                f"pressure_reading={pressure:.2f} bar (not trusted as gate) → priming line"
            )
            self._complete_pressurisation()

    def _complete_pressurisation(self):
        mat = material_state_manager.state
        now = time.time()
        program_state.on_pressurised()  # → LINE_PRIMING
        self._prime_start_ts = now
        current_kg = mat.current_pot_kg or 0.0
        self._prime_start_weight = current_kg
        self._rate_window_start_weight = current_kg
        self._rate_window_start_weight = current_kg
        self._peak_drop_rate = 0.0
        self._nozzle_cracked = False
        self._nozzle_crack_ts = 0.0
        start_kg = mat.current_pot_kg or 0.0

        print(
            f"[STARTUP_ORCH] Pressurisation complete — "
            f"starting line prime from {start_kg:.3f}kg"
        )

    # ──────────────────────────────────────────────────────────────
    # PHASE 3: LINE PRIMING
    #
    # Physical sequence in your 5ft × 1/2" + spring nozzles system:
    #   Phase A: Air in line exits — very low weight drop (air has no mass)
    #   Phase B: Paint fills line slowly — steady weight drop
    #   Phase C: Nozzles crack open — weight drop rate INCREASES briefly
    #   Phase D: Stable flow — rate settles at ongoing dispense rate = PRIMED
    #
    # Detection: watch for rate to increase above nozzle_crack_rate_kg_s,
    # then confirm it stays elevated for stable_confirm_s.
    # ──────────────────────────────────────────────────────────────
    def _handle_line_priming(self, mat):

        weight_valid = (
            mat.current_pot_kg is not None
            and mat.current_pot_kg > 0
        )
        
        from app.commands.helpers import create_and_queue_command
        p = self.profile
        now = time.time()

        # ── Send prime_start once ──
        if not self._prime_cmd_sent:
            print(
                f"[STARTUP_ORCH] Opening dispense valve — priming line "
                f"(profile={p.name}, min={p.line_prime_min_time_s}s, "
                f"timeout={p.line_prime_timeout_s}s)"
            )
            create_and_queue_command(
                name="line.prime_start",
                payload={"timeout_ms": int(p.line_prime_timeout_s * 1000)}
            )
            self._prime_cmd_sent = True
            self._prime_start_ts = now
            self._prime_start_weight = mat.current_pot_kg or 0.0
            self._rate_window_start_ts = now
            self._rate_window_start_weight = mat.current_pot_kg
            return

        elapsed = now - self._prime_start_ts

        if elapsed > p.line_prime_timeout_s:
            print(
                f"[STARTUP_ORCH] WARNING: Prime timeout — forcing completion"
            )

            if not self._prime_stop_sent:
                create_and_queue_command(name="line.prime_stop", payload={})
                self._prime_stop_sent = True
                program_state.on_line_primed()
                material_state_manager.state.line_primed = True

            return
        

        # total_drain_kg = self._prime_start_weight - mat.current_pot_kg

        current_kg = mat.current_pot_kg or 0.0
        start_kg = self._prime_start_weight or current_kg

        total_drain_kg = start_kg - current_kg

        if total_drain_kg >= p.line_prime_max_drain_kg:
            print(
                f"[STARTUP_ORCH] WARNING: Excess drain ignored in test mode "
                f"{total_drain_kg:.3f}kg"
            )
        
        if self.TEST_MODE:
            if elapsed > 3:
                print("[STARTUP_ORCH] TEST MODE forcing line primed")
                create_and_queue_command(name="line.prime_stop", payload={})
                self._prime_stop_sent = True
                program_state.on_line_primed()
                material_state_manager.state.line_primed = True
            return

       # ── Fixed duration priming ──
        if elapsed >= p.line_prime_min_time_s:

            print(
                f"[STARTUP_ORCH] Prime duration complete "
                f"({elapsed:.1f}s) — closing valve"
            )

            if not self._prime_stop_sent:
                create_and_queue_command(name="line.prime_stop", payload={})
                self._prime_stop_sent = True
                program_state.on_line_primed()
                material_state_manager.state.line_primed = True

            return

        # ─────────────────────────────────────────
        # Fallback: weight invalid → time-based prime
        # ─────────────────────────────────────────
        if not weight_valid:
            if (
                not self._prime_stop_sent
                and elapsed >= p.line_prime_min_time_s
            ):
                print("[STARTUP_ORCH] Weight invalid — assuming primed (time-based)")
                create_and_queue_command(name="line.prime_stop", payload={})
                # self._emit_event("line.prime_stop")
                self._prime_stop_sent = True
                program_state.on_line_primed()
                material_state_manager.state.line_primed = True
            return

        # ── Hard timeout ──
        # if elapsed > p.line_prime_timeout_s:
        #     print(
        #         f"[STARTUP_ORCH] ABORT: Line prime timeout after {elapsed:.0f}s "
        #         f"({total_drain_kg*1000:.0f}g drained)"
        #     )
        #     create_and_queue_command(name="line.prime_stop", payload={})
        #     program_state.abort("line_prime_timeout")
        #     return



        # ── Safety drain cap ──
        # if total_drain_kg >= p.line_prime_max_drain_kg:
        #     print(
        #         f"[STARTUP_ORCH] ABORT: Line prime safety cap — "
        #         f"{total_drain_kg:.3f}kg drained (max={p.line_prime_max_drain_kg}kg)"
        #     )
        #     create_and_queue_command(name="line.prime_stop", payload={})
        #     program_state.abort("line_prime_excess_drain")
        #     return

        # ── Compute rate every rate_window_s ──
        rate_window_elapsed = now - self._rate_window_start_ts
        if rate_window_elapsed < p.line_prime_rate_window_s:
            return   # not time to sample yet

        weight_in_window = self._rate_window_start_weight - mat.current_pot_kg
        # current_rate = weight_in_window / rate_window_elapsed  # kg/s (positive = drain)

        if rate_window_elapsed <= 0:
            return
        current_rate = weight_in_window / rate_window_elapsed


        # Update peak
        if current_rate > self._peak_drop_rate:
            self._peak_drop_rate = current_rate

        # Reset window
        self._rate_window_start_ts = now
        self._rate_window_start_weight = mat.current_pot_kg

        print(
            f"[STARTUP_ORCH] Line prime: elapsed={elapsed:.0f}s "
            f"drained={total_drain_kg*1000:.0f}g "
            f"rate={current_rate*1000:.1f}g/s "
            f"peak={self._peak_drop_rate*1000:.1f}g/s "
            f"nozzle_crack_threshold={p.line_prime_nozzle_crack_rate_kg_s*1000:.1f}g/s"
        )

        # ── Only check for prime after minimum time ──
        # if elapsed < p.line_prime_min_time_s:
        #     return

        # # ── Nozzle crack detection: rate exceeded threshold ──
        # if not self._nozzle_cracked:
        #     if current_rate >= p.line_prime_nozzle_crack_rate_kg_s:
        #         self._nozzle_cracked = True
        #         self._nozzle_crack_ts = now
        #         print(
        #             f"[STARTUP_ORCH] Nozzle crack detected — "
        #             f"rate={current_rate*1000:.1f}g/s at t={elapsed:.0f}s"
        #         )
        #     return  # wait for crack before confirming

        # ── Detect crack immediately (do NOT wait for min time) ──
        # if not self._nozzle_cracked:
        #     if current_rate >= p.line_prime_nozzle_crack_rate_kg_s:
        #         self._nozzle_cracked = True
        #         self._nozzle_crack_ts = now
        #         print(
        #             f"[STARTUP_ORCH] Nozzle crack detected — "
        #             f"rate={current_rate*1000:.1f}g/s at t={elapsed:.0f}s"
        #         )

 

        # # If crack not yet detected → cannot finish
        # if not self._nozzle_cracked:
        #     return

        # Only allow completion AFTER minimum prime time
        # if elapsed < p.line_prime_min_time_s:
        #     return


        # ─────────────────────────────────────────
        # HARD DRAIN SAFETY (industrial protection)
        # ─────────────────────────────────────────

        # if total_drain_kg >= 0.7:   # 700g max physical allowance
        #     print(
        #         f"[STARTUP_ORCH] SAFETY: Excess drain "
        #         f"{total_drain_kg:.3f}kg — closing prime valve"
        #     )

        #     if not self._prime_stop_sent:
        #         create_and_queue_command(name="line.prime_stop", payload={})
        #         self._prime_stop_sent = True
        #         program_state.abort("line_prime_excess_drain")

        #     return

        # ─────────────────────────────────────────
        # Finish priming immediately after:
        #   1) Nozzle crack detected
        #   2) Minimum prime time satisfied
        # ─────────────────────────────────────────

        # if self._nozzle_cracked and elapsed >= p.line_prime_min_time_s:

        #     print(
        #         f"[STARTUP_ORCH] Line PRIMED — "
        #         f"crack_detected elapsed={elapsed:.1f}s "
        #         f"total_drain={total_drain_kg*1000:.0f}g"
        #     )

        #     if not self._prime_stop_sent:
        #         create_and_queue_command(name="line.prime_stop", payload={})
        #         self._prime_stop_sent = True
        #         program_state.on_line_primed()
        #         material_state_manager.state.line_primed = True

        #     return


        # ── Confirm stable flow after crack ──
        # time_since_crack = now - self._nozzle_crack_ts
        # if time_since_crack >= p.line_prime_stable_confirm_s:
        #     print(
        #         f"[STARTUP_ORCH] Line PRIMED — "
        #         f"stable for {time_since_crack:.1f}s after nozzle crack "
        #         f"total_drain={total_drain_kg*1000:.0f}g elapsed={elapsed:.0f}s"
        #     )
        #     # create_and_queue_command(name="line.prime_stop", payload={})
        #     # program_state.on_line_primed()   # → READY
        #     # material_state_manager.state.line_primed = True

        #     if not hasattr(self, "_prime_stop_sent"):
        #         self._prime_stop_sent = False

        #     if not self._prime_stop_sent:
        #         create_and_queue_command(name="line.prime_stop", payload={})
        #         self._prime_stop_sent = True
        #         program_state.on_line_primed()
        #         material_state_manager.state.line_primed = True



startup_orchestrator = StartupOrchestrator()
