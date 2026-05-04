# app/orchestrators/startup_orchestrator.py

import time
from app.state.program_state import program_state, ProgramPhase
from app.state.material_state import material_state_manager
from app.state.machine_state import machine_state_manager
from app.config.paint_profile import PaintProfile, DEFAULT_PROFILE


class StartupOrchestrator:
    """
    Startup sequence:
        PRESSURISE_POT → PRESSURISING → LINE_PRIMING → READY

    All timing from PaintProfile.
    """

    def __init__(self):
        self.profile: PaintProfile = DEFAULT_PROFILE
        self.TEST_MODE = False
        self.executor = None
        self._reset_state()

    def _reset_state(self):
        self._pressurise_stage = "IDLE"
        self._active_cmd = None
        self._started = False
        # CHANGE 1: track actual pot pressurise duration so we can
        # seed program_engine's pressure model accurately on completion
        self._pot_pressurise_open_s = 0.0

        # Pressurise phase (passthrough — pot pressurised inside fill)
        self._pressurise_cmd_sent = False
        self._pressurise_stop_sent = False
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
        self._reset_state()
        print("[STARTUP_ORCH] Reset")

    # def begin(self, profile: PaintProfile = None):
    #     if profile:
    #         self.profile = profile

    #     mat = material_state_manager.state
    #     now = time.time()

    #     current_kg = mat.current_pot_kg or 0.0
    #     # target_kg = self.profile.pot_fill_target_kg

    #     # fill_threshold = target_kg * 0.9
    #     # if current_kg >= fill_threshold:
    #     #     from app.commands.helpers import create_and_queue_command
    #     #     print(
    #     #         f"[STARTUP_ORCH] Pot already at {current_kg:.3f}kg "
    #     #         f"(>= 90% target {fill_threshold:.3f}kg) — skipping fill, "
    #     #         f"going straight to pot pressurise"
    #     #     )
    #     #     program_state.begin_pot_filling()
    #     #     self._pressurise_stage = "PRESSURISE_POT"
    #     #     return

    #     # self._fill_phase_start_ts = now
    #     # self._fill_phase_start_weight = current_kg

    #     # program_state.begin_pot_filling()
    #     # self._pressurise_stage = "OPEN_VENT"

    #     if self.TEST_MODE:
    #         print("[STARTUP_ORCH] TEST MODE ENABLED — bypassing sensors")

    #     # print(
    #     #     f"[STARTUP_ORCH] begin() — profile={self.profile.name} "
    #     #     f"pot_now={current_kg:.3f}kg "
    #     #     f"target={target_kg}kg (fill to 90% = {fill_threshold:.3f}kg)"
    #     )

    def begin(self, profile: PaintProfile = None):
        if profile:
            self.profile = profile
        self._started = True   # 🔴 ADD THIS
        # program_state.begin_pot_filling()
        program_state.set_phase(ProgramPhase.PRESSURISING, "startup_pressurise_begin")
        self._pressurise_stage = "PRESSURISE_POT"

        print("[STARTUP_ORCH] Begin → PRESSURISE_POT (fill disabled)")

    # def _adjust_pressure_after_prime(self, elapsed):
    #     try:
    #         import app.program.program_engine as program_module
    #         if program_module.program_engine:
    #             p = self.profile
    #             drop = elapsed * p.pressure_dispense_bleed_mpa_per_s

    #             program_module.program_engine._estimated_pressure_mpa = max(
    #                 0.0,
    #                 program_module.program_engine._estimated_pressure_mpa - drop
    #             )

    #             print(f"[STARTUP_ORCH] Adjusted pressure after prime (drop={drop:.4f})")

    #     except Exception as e:
    #         print(f"[STARTUP_ORCH] Pressure adjust failed: {e}")

    def _adjust_pressure_after_prime(self, elapsed):
        try:
            import app.program.program_engine as program_module
            eng = program_module.program_engine
            if eng:
                cost = elapsed * (1.0 / 9.0) * 3.0  # dispense bleeds ~3x faster than idle
                eng._credits = max(0.0, eng._credits - cost)
                print(f"[STARTUP_ORCH] Prime credit cost={cost:.3f} credits={eng._credits:.3f}")
        except Exception as e:
            print(f"[STARTUP_ORCH] Prime adjust failed: {e}")

    # ──────────────────────────────────────────────────────────────
    # Tick router
    # ──────────────────────────────────────────────────────────────
    def process(self):
        ps = program_state
        mat = material_state_manager.state
        ms = machine_state_manager.state

        # if ps.phase == ProgramPhase.POT_FILLING:
        #     self._handle_pot_filling(mat)
        # if ps.phase == ProgramPhase.PRESSURISING:
        #     self._handle_pressurising(ms)

        if ps.phase == ProgramPhase.PRESSURISING:
            if self._pressurise_stage != "DONE":
                self._handle_pressurisation(mat)
            else:
                self._handle_pressurising(ms)
                
        # elif ps.phase == ProgramPhase.LINE_PRIMING:
        #     self._handle_line_priming(mat)

        elif ps.phase == ProgramPhase.READY:

            print("[STARTUP_ORCH] READY — control returned to ProgramEngine")
            from app.modes.mode_manager import mode_manager
            from app.modes.mode_types import OperationMode, ProcessMode

            mode_manager.set_operation(OperationMode.auto)
            mode_manager.set_process(ProcessMode.tracking)

            print("[STARTUP_ORCH] Modes set → auto / tracking")
            return

    # def _handle_pressurisation(self, mat):
    #     from app.commands.helpers import create_and_queue_command
    #     p = self.profile
    #     now = time.time()

    #     # STEP 1: PRESSURISE POT
    #     if self._pressurise_stage == "PRESSURISE_POT":
    #         if not self._active_cmd:
    #             print("[STARTUP] Pressurising pot")
    #             self._active_cmd = create_and_queue_command(
    #                 name="pot.pressurise",
    #                 payload={}
    #             )
    #             self._pot_pressurise_ts = now
    #             return

    #         elapsed = now - self._pot_pressurise_ts

    #         # 🔴 SAFETY GUARD (ADD HERE)
    #         if elapsed > p.pressure_charge_time_s + 5:
    #             print("[STARTUP] WARNING: forcing stop (timeout)")
    #             self._pot_pressurise_open_s = elapsed
    #             self._active_cmd = None
    #             self._pressurise_stage = "STOP_POT_PRESSURISE"
    #             return

    #         if self.executor.is_completed(self._active_cmd):

    #             if elapsed >= p.pressure_charge_time_s:
    #                 print(f"[STARTUP] Pot pressurised ({elapsed:.1f}s)")
    #                 self._pot_pressurise_open_s = elapsed
    #                 self._active_cmd = None
    #                 self._pressurise_stage = "STOP_POT_PRESSURISE"
    #         return

    #     # STEP 2: STOP PRESSURE
    #     if self._pressurise_stage == "STOP_POT_PRESSURISE":
    #         if not self._active_cmd:
    #             self._active_cmd = create_and_queue_command(
    #                 name="pot.pressurise_stop",
    #                 payload={}
    #             )
    #             return

    #         if self.executor.is_completed(self._active_cmd):
    #             self._active_cmd = None
    #             self._pressurise_stage = "COMPLETE"

    #     # STEP 3: COMPLETE
    #     if self._pressurise_stage == "COMPLETE":
    #         print("[STARTUP] Pressurise complete → LINE_PRIMING")
    #         program_state.on_pressurised()

    #         self._pressurise_stage = "DONE"

    def is_started(self):
        return getattr(self, "_started", False)

    def _handle_pressurisation(self, mat):
        from app.commands.helpers import create_and_queue_command
        p = self.profile
        now = time.time()

        # STEP 1: PRESSURISE POT
        if self._pressurise_stage == "PRESSURISE_POT":
            if not self._active_cmd:
                print("[STARTUP] Pressurising pot")
                self._active_cmd = create_and_queue_command(
                    name="pot.pressurise",
                    payload={}
                )
                self._pot_pressurise_ts = now
                return

            elapsed = now - self._pot_pressurise_ts

            # SAFETY GUARDFline
            if elapsed > p.pressure_charge_time_s + 5:
                print("[STARTUP] WARNING: forcing stop (timeout)")
                self._pot_pressurise_open_s = elapsed
                self._active_cmd = None
                self._pressurise_stage = "STOP_POT_PRESSURISE"
                return

            # ✅ TIME-BASED COMPLETION (FIXED)
            if elapsed >= p.pressure_charge_time_s:
                print(f"[STARTUP] Pot pressurised ({elapsed:.1f}s)")
                self._pot_pressurise_open_s = elapsed
                self._active_cmd = None
                print("[DEBUG] cleared active_cmd")
                self._pressurise_stage = "STOP_POT_PRESSURISE"
                return
            return

        # # STEP 2: STOP PRESSURE
        # if self._pressurise_stage == "STOP_POT_PRESSURISE":
        #     if not self._active_cmd:
        #         self._active_cmd = create_and_queue_command(
        #             name="pot.pressurise_stop",
        #             payload={}
        #         )
        #         return

        #     # ✅ NO EXECUTOR DEPENDENCY
        #     self._active_cmd = None
        #     self._pressurise_stage = "COMPLETE"

        if self._pressurise_stage == "STOP_POT_PRESSURISE":
            print("[STARTUP] Sending pressurise_stop")

            create_and_queue_command(
                name="pot.pressurise_stop",
                payload={}
            )

            # 🔴 DO NOT WAIT
            self._active_cmd = None
            self._pressurise_stage = "COMPLETE"
            return

        # STEP 3: COMPLETE
        if self._pressurise_stage == "COMPLETE":
            print("[STARTUP] Pressurise complete → READY (no priming)")
           

            # 🔴 ADD THIS (CRITICAL FIX)
            try:
                import app.program.program_engine as program_module
                from app.state.material_state import material_state_manager

                mat = material_state_manager.state
                current_kg = mat.current_pot_kg or self.profile.pressure_model_ref_kg

                if program_module.program_engine:
                    program_module.program_engine.seed_pressure(
                        open_s=self._pot_pressurise_open_s,
                        current_kg=current_kg
                    )
                    print("[STARTUP_ORCH] Seeded pressure model after pressurise")

            except Exception as e:
                print(f"[STARTUP_ORCH] Pressure seed failed: {e}")


            material_state_manager.state.line_primed = True
            # program_state.on_pressurised()
            # print("[DEBUG] phase should now be LINE_PRIMING")
            # self._pressurise_stage = "DONE"

            program_state.set_phase(ProgramPhase.READY, "startup_no_prime")
            print("[STARTUP_ORCH] Skipping line priming → READY")

            self._pressurise_stage = "DONE"


    # ─────────────────────────────────────────────────────────────
    # PHASE 2: PRESSURISING — passthrough
    # Pot is already pressurised inside the fill sequence.
    # Just seed the pressure model and transition to LINE_PRIMING.
    # ──────────────────────────────────────────────────────────────
    def _handle_pressurising(self, ms):
        if not self._pressurise_cmd_sent:
            print("[STARTUP_ORCH] Pot already pressurised — seeding pressure model → line prime")
            self._pressurise_cmd_sent = True

            # CHANGE 4: seed program_engine's pressure model with the
            # actual open duration recorded in PRESSURISE_POT.
            # This sets estimated_pressure_mpa to the correct starting
            # value so maintenance pulses don't fire unnecessarily early.
            mat = material_state_manager.state
            current_kg = mat.current_pot_kg or self.profile.pressure_model_ref_kg
            # self._seed_program_engine_pressure(
            #     open_s=self._pot_pressurise_open_s,
            #     current_kg=current_kg
            # )

            self._complete_pressurisation()

    # def _seed_program_engine_pressure(self, open_s: float, current_kg: float):
    #     """Notify program_engine of how much pot_air_in time was banked."""
    #     try:
    #         import app.program.program_engine as program_module
    #         if program_module.program_engine is not None:
    #             program_module.program_engine.seed_pressure(open_s=open_s, current_kg=current_kg)
    #     except Exception as e:
    #         print(f"[STARTUP_ORCH] Could not seed pressure model: {e}")

    def _complete_pressurisation(self):
        mat = material_state_manager.state
        now = time.time()
        self._prime_start_ts = now
        current_kg = mat.current_pot_kg or 0.0
        self._prime_start_weight = current_kg
        self._rate_window_start_ts = now
        self._rate_window_start_weight = current_kg
        self._peak_drop_rate = 0.0
        self._nozzle_cracked = False
        self._nozzle_crack_ts = 0.0
        print(f"[STARTUP_ORCH] Ready to prime line from {current_kg:.3f}kg")

    # ──────────────────────────────────────────────────────────────
    # PHASE 3: LINE PRIMING
    # ──────────────────────────────────────────────────────────────
    # def _handle_line_priming(self, mat):
    #     weight_valid = (
    #         mat.current_pot_kg is not None
    #         and mat.current_pot_kg > 0
    #     )

    #     from app.commands.helpers import create_and_queue_command
    #     p = self.profile
    #     now = time.time()

    #     if not self._prime_cmd_sent:
    #         print(
    #             f"[STARTUP_ORCH] Opening dispense valve — priming line "
    #             f"(profile={p.name}, min={p.line_prime_min_time_s}s, "
    #             f"timeout={p.line_prime_timeout_s}s)"
    #         )
    #         create_and_queue_command(
    #             name="line.prime_start",
    #             payload={"timeout_ms": int(p.line_prime_timeout_s * 1000)}
    #         )
    #         self._prime_cmd_sent = True
    #         self._prime_start_ts = now
    #         self._prime_start_weight = mat.current_pot_kg or 0.0
    #         self._rate_window_start_ts = now
    #         self._rate_window_start_weight = mat.current_pot_kg
    #         return

    #     elapsed = now - self._prime_start_ts

    #     # Hard timeout
    #     if elapsed > p.line_prime_timeout_s:
    #         print("[STARTUP_ORCH] WARNING: Prime timeout — forcing completion")
    #         if not self._prime_stop_sent:
    #             create_and_queue_command(name="line.prime_stop", payload={})
    #             self._prime_stop_sent = True
    #             program_state.set_phase(ProgramPhase.READY, "line_primed")

    #             self._adjust_pressure_after_prime(elapsed)

    #             print(f"[DEBUG] CURRENT PHASE AFTER PRIME: {program_state.phase}")

    #             material_state_manager.state.line_primed = True

    #             self._prime_cmd_sent = False
    #             self._prime_stop_sent = False

    #             # self._reseed_after_prime(elapsed)
    #             # program_state.on_line_primed()
    #             # material_state_manager.state.line_primed = True
    #             # self._reseed_after_prime(elapsed)
    #             # CHANGE 5: after prime, pressure has bled due to dispense
    #             # being open for prime duration. Re-seed so model reflects
    #             # that pressure has dropped by (elapsed × dispense_bleed_rate).
    #         return

    #     current_kg = mat.current_pot_kg or 0.0
    #     start_kg = self._prime_start_weight or current_kg
    #     total_drain_kg = start_kg - current_kg

    #     if total_drain_kg >= p.line_prime_max_drain_kg:
    #         print(
    #             f"[STARTUP_ORCH] WARNING: Excess drain "
    #             f"{total_drain_kg:.3f}kg (max={p.line_prime_max_drain_kg}kg)"
    #         )

    #     if self.TEST_MODE:
    #         if elapsed > 3:
    #             print("[STARTUP_ORCH] TEST MODE forcing line primed")
    #             create_and_queue_command(name="line.prime_stop", payload={})
    #             self._prime_stop_sent = True

    #             program_state.set_phase(ProgramPhase.READY, "line_primed")

    #             self._adjust_pressure_after_prime(elapsed)


    #             print(f"[DEBUG] CURRENT PHASE AFTER PRIME: {program_state.phase}")

    #             material_state_manager.state.line_primed = True

    #             self._prime_cmd_sent = False
    #             self._prime_stop_sent = False

    #             # self._reseed_after_prime(elapsed)


    #             # program_state.on_line_primed()
    #             # material_state_manager.state.line_primed = True
    #             # self._reseed_after_prime(elapsed)
    #         return

    #     # Fixed duration prime — primary completion gate
    #     if elapsed >= p.line_prime_min_time_s:
    #         print(
    #             f"[STARTUP_ORCH] Prime duration complete "
    #             f"({elapsed:.1f}s) — closing valve"
    #         )
    #         if not self._prime_stop_sent:
    #             create_and_queue_command(name="line.prime_stop", payload={})
    #             self._prime_stop_sent = True

    #             program_state.set_phase(ProgramPhase.READY, "line_primed")

    #             self._adjust_pressure_after_prime(elapsed)

    #             print(f"[DEBUG] CURRENT PHASE AFTER PRIME: {program_state.phase}")

    #             material_state_manager.state.line_primed = True

    #             self._prime_cmd_sent = False
    #             self._prime_stop_sent = False

    #             # self._reseed_after_prime(elapsed)


    #             # program_state.on_line_primed()
    #             # material_state_manager.state.line_primed = True
    #             # self._reseed_after_prime(elapsed)
    #             # CHANGE 5 (same): re-seed pressure model after prime
    #         return

    #     # Weight invalid fallback
    #     if not weight_valid:
    #         if not self._prime_stop_sent and elapsed >= p.line_prime_min_time_s:
    #             print("[STARTUP_ORCH] Weight invalid — assuming primed (time-based)")
    #             create_and_queue_command(name="line.prime_stop", payload={})
    #             self._prime_stop_sent = True

    #             program_state.set_phase(ProgramPhase.READY, "line_primed")

    #             self._adjust_pressure_after_prime(elapsed)

    #             print(f"[DEBUG] CURRENT PHASE AFTER PRIME: {program_state.phase}")

    #             material_state_manager.state.line_primed = True

    #             self._prime_cmd_sent = False
    #             self._prime_stop_sent = False

    #             # self._reseed_after_prime(elapsed)

    #             # program_state.on_line_primed()
    #             # material_state_manager.state.line_primed = True
    #             # self._reseed_after_prime(elapsed)
    #         return

    #     # Rate window sampling (logging only)
    #     rate_window_elapsed = now - self._rate_window_start_ts
    #     if rate_window_elapsed < p.line_prime_rate_window_s or rate_window_elapsed <= 0:
    #         return

    #     weight_in_window = self._rate_window_start_weight - mat.current_pot_kg
    #     current_rate = weight_in_window / rate_window_elapsed

    #     if current_rate > self._peak_drop_rate:
    #         self._peak_drop_rate = current_rate

    #     self._rate_window_start_ts = now
    #     self._rate_window_start_weight = mat.current_pot_kg

    #     print(
    #         f"[STARTUP_ORCH] Line prime: elapsed={elapsed:.0f}s "
    #         f"drained={total_drain_kg*1000:.0f}g "
    #         f"rate={current_rate*1000:.1f}g/s "
    #         f"peak={self._peak_drop_rate*1000:.1f}g/s "
    #         f"crack_threshold={p.line_prime_nozzle_crack_rate_kg_s*1000:.1f}g/s"
    #     )

    # def _reseed_after_prime(self, prime_elapsed_s: float):
    #     """
    #     CHANGE 5: After line priming, the dispense valve was open for
    #     prime_elapsed_s seconds. Pressure bled at dispense_bleed_rate
    #     the whole time. Subtract that from the model so the maintenance
    #     pulse fires immediately if needed instead of waiting based on a
    #     stale (too-high) estimate.

    #     Example: pot pressurised to 0.35 MPa, then prime ran for 5s.
    #       pressure_drop = 5 × 0.05 = 0.25 MPa
    #       estimated after prime = max(0, 0.35 - 0.25) = 0.10 MPa
    #       → below 0.28 → maintenance pulse fires as soon as READY
    #     """
    #     try:
    #         import app.program.program_engine as program_module
    #         if program_module.program_engine is not None:
    #             p = self.profile
    #             drop = prime_elapsed_s * p.pressure_dispense_bleed_mpa_per_s
    #             program_module.program_engine._estimated_pressure_mpa = max(
    #                 0.0,
    #                 program_module.program_engine._estimated_pressure_mpa - drop
    #             )
    #             print(
    #                 f"[STARTUP_ORCH] Pressure re-seeded after prime — "
    #                 f"prime={prime_elapsed_s:.1f}s "
    #                 f"drop={drop:.4f} MPa "
    #                 f"estimated={program_module.program_engine._estimated_pressure_mpa:.4f} MPa"
    #             )
    #     except Exception as e:
    #         print(f"[STARTUP_ORCH] Could not re-seed pressure after prime: {e}")


startup_orchestrator = StartupOrchestrator()