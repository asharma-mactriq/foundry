# app/program/program_engine.py

import time

from app.state.program_state import program_state, ProgramPhase
from app.state.material_state import material_state_manager
from app.services.command_executor import CommandExecutor
from app.config.paint_profile import PaintProfile, get_profile, DEFAULT_PROFILE



class ProgramEngine:
    """
    Drives program lifecycle:
      start_program() → STARTED → LOADED
          → startup_orchestrator.begin() takes over →
     PRESSURISING → LINE_PRIMING → READY → RUNNING


    Pressure model — physical basis:
      Working range:        0.28 – 0.35 MPa
      Charge rate:          0.35 MPa / 9s ≈ 0.0389 MPa/s  (full pot)
      Idle bleed:           0.00117 MPa/s  (solenoid closed, ~5min to zero)
      Dispense bleed:       0.05 MPa/s    (solenoid open)

      Derived:
        Idle: 60s to bleed from 0.35 → 0.28 — top-up fires around 50s idle
        Dispense: 1.4s to bleed 0.35 → 0.28 during active dispense
        Top-up from 0.28 → 0.35: ~1.8s of pot_air_in

    """

    def __init__(self, executor: CommandExecutor):
        self.executor = executor
        self.config: dict = {}
        self.profile: PaintProfile = DEFAULT_PROFILE
        self._reset_pressure_state()
        self._estimated_pressure_mpa = self.profile.pressure_high_mpa
        self._ready_initialized = False
        self._skip_n = 3
        self._last_weight = None
        self._window_drop_sum = 0.0
        self._pass_window = 0
        self._prev_gap = 0


    # ──────────────────────────────────────────────────────────────
    # Pressure model state
    # ──────────────────────────────────────────────────────────────
    def _reset_pressure_state(self):
        # Estimated pot pressure in MPa — the single number we track
        self._estimated_pressure_mpa: float = 0.0

        # Timestamp of last model update (used to compute elapsed per tick)
        self._pressure_last_ts: float = time.time()

        # True while pot_air_in is open for a top-up pulse
        self._pressure_pulse_active: bool = False

        # Timestamp when current pulse opened
        self._pressure_pulse_start_ts: float = 0.0

        # True after pressurise_stop sent — clear next tick
        self._pressure_stop_sent: bool = False

        # Timestamp when last pulse completed (for cooldown)
        self._pressure_pulse_end_ts: float = 0.0

    def seed_pressure(self, open_s: float, current_kg: float):
        """
        Called after any pot_air_in open event (startup pressurise,
        mid-refill repressurise) so the model starts accurately.

        Computes how much pressure was built by that open duration,
        accounting for current paint weight (headspace).
        """
        p = self.profile
        charge_rate = self._charge_rate_mpa_per_s(current_kg)
        gained = charge_rate * open_s
        self._estimated_pressure_mpa = min(
            self._estimated_pressure_mpa + gained,
            p.pressure_high_mpa
        )
        self._pressure_last_ts = time.time()
        print(
            f"[PRESSURE_MODEL] Seeded — open_s={open_s:.1f}s "
            f"charge_rate={charge_rate:.5f} MPa/s "
            f"gained={gained:.4f} MPa "
            f"estimated={self._estimated_pressure_mpa:.4f} MPa"
        )

    def _charge_rate_mpa_per_s(self, current_kg: float) -> float:
        """
        How fast pot pressurises at current fill weight.
        More paint = less headspace = faster charge.
        charge_rate = (pressure_high / charge_time_s) * (current_kg / ref_kg) * factor
        """
        p = self.profile
        if current_kg <= 0:
            current_kg = p.pressure_model_ref_kg
        base_rate = p.pressure_high_mpa / p.pressure_charge_time_s
        weight_ratio = current_kg / p.pressure_model_ref_kg
        return base_rate * weight_ratio * p.pressure_model_headspace_factor

    def _update_pressure_model(self, now: float, dispensing_active: bool):
        """
        Tick the pressure model:
          - Apply bleed (idle or dispense rate) for elapsed time
          - If pulse active, apply charge for elapsed time
          - Clamp to [0, pressure_high_mpa]
        """
        p = self.profile
        mat = material_state_manager.state
        elapsed = now - self._pressure_last_ts
        self._pressure_last_ts = now

        if elapsed <= 0:
            return

        # Apply bleed
        if dispensing_active:
            bleed = p.pressure_dispense_bleed_mpa_per_s * elapsed
        else:
            bleed = p.pressure_idle_bleed_mpa_per_s * elapsed

        self._estimated_pressure_mpa = max(
            0.0,
            self._estimated_pressure_mpa - bleed
        )

        # Apply charge if pot_air_in open
        if self._pressure_pulse_active:
            current_kg = mat.current_pot_kg or p.pressure_model_ref_kg
            charge = self._charge_rate_mpa_per_s(current_kg) * elapsed
            self._estimated_pressure_mpa = min(
                self._estimated_pressure_mpa + charge,
                p.pressure_high_mpa
            )

    # ──────────────────────────────────────────────────────────────
    # API
    # ──────────────────────────────────────────────────────────────
    def start_program(self, config: dict):
        print(f"[PROGRAM_ENGINE] START PROGRAM config={config}")
        self.config = config
        self._ready_initialized = False
        profile_name = config.get("paint_profile")
        self.profile = get_profile(profile_name)

        # self.mid_refill_orchestrator.reset()
        self._reset_pressure_state()
        self._estimated_pressure_mpa = self.profile.pressure_high_mpa
        self._pressure_last_fire_ts = time.time()   # 🔴 ADD THIS

        from app.orchestrators.startup_orchestrator import startup_orchestrator
        startup_orchestrator.reset()

        program_state.start_program()

        self.executor.send_command({
            "name": "program.load",
            "payload": {"program_id": config.get("program_id", "default")}
        })

    def abort(self, reason: str = None):
        from app.modes.mode_manager import mode_manager
        from app.modes.mode_types import OperationMode, ProcessMode
        program_state.set_phase(ProgramPhase.ABORT, reason or "abort")
        mode_manager.set_operation(OperationMode.manual)
        mode_manager.set_process(ProcessMode.idle)

    def stop_program(self):
        print("[PROGRAM_ENGINE] STOP PROGRAM")
        from app.modes.mode_manager import mode_manager
        from app.modes.mode_types import OperationMode, ProcessMode

        self.executor.send_command({"name": "program.stop", "payload": {}})
        program_state.stop_program()

        mode_manager.set_operation(OperationMode.manual)
        mode_manager.set_process(ProcessMode.idle)
        print("[PROGRAM_ENGINE] Modes reset → manual/idle")

    # ──────────────────────────────────────────────────────────────
    # Main event loop — called every telemetry tick
    # ──────────────────────────────────────────────────────────────
    def on_event(self, machine, program):
        ps = program
        mat = material_state_manager.state

        # if ps.last_event:
        #     print(f"[PROGRAM_ENGINE] event={ps.last_event} phase={ps.phase}")
        #     ps.last_event = None   # ✅ ADD THIS LINE

        if ps.phase == ProgramPhase.STARTED:
            return

        # 🔴 STARTUP TRIGGER (critical)
        from app.orchestrators.startup_orchestrator import startup_orchestrator

        if ps.phase in (ProgramPhase.LOADED, ProgramPhase.STARTUP) and not startup_orchestrator.is_started():
            from app.orchestrators.startup_orchestrator import startup_orchestrator
            print("[PROGRAM_ENGINE] LOADED → starting startup orchestrator")
            program_state.begin_startup()   # 🔴 ADD THIS LINE
            startup_orchestrator.begin(self.profile)
            return

        # if ps.phase in (
        #     ProgramPhase.PRESSURISING,
        #     ProgramPhase.LINE_PRIMING,
        # ):
        #     from app.orchestrators.startup_orchestrator import startup_orchestrator
        #     startup_orchestrator.process()
        #     return
        
# 🔴 CRITICAL FIX — reset gap memory when entering READY

        # if ps.phase == ProgramPhase.MID_REFILLING:
        #     self.mid_refill_orchestrator.process()
        #     return


        gap = getattr(machine, "gap", 0)
        if ps.phase == ProgramPhase.READY and not self._ready_initialized:
            print("[ENGINE] READY entered — resetting gap state")
            self._prev_gap = 0
            self._ready_initialized = True

        # if not hasattr(self, "_prev_gap"):
        #     self._prev_gap = 0

        if ps.phase in (ProgramPhase.READY, ProgramPhase.RUNNING):

            if gap == 1 and self._prev_gap == 0:
                ps.new_pass()

            elif gap == 1 and self._prev_gap == 1:
                if ps.current_pass > 0:
                    ps.mark_stable(ps.current_pass)

            elif gap == 0 and self._prev_gap == 1:
                if ps.current_pass > 0:
                    ps.mark_exit(ps.current_pass)

        self._prev_gap = gap


        if ps.phase not in (ProgramPhase.READY, ProgramPhase.RUNNING):
            return

        # ── RUNNING / READY ───────────────────────────────────────
        now = time.time()

        # Tick pressure model — must happen every tick regardless
        dispensing_active = getattr(mat, "dispensing_active", False)

        if ps.phase in (ProgramPhase.RUNNING, ProgramPhase.READY):
            self._update_pressure_model(now, dispensing_active)
        # self._update_pressure_model(now, dispensing_active)

        # Step 1: Pressure maintenance — returns True if pot_air_in
        # is open or a command was just sent. Block everything else.
        if self._maintain_pressure(now, mat):
            return
        # self._maintain_pressure(now, mat)
        # # Step 2: Mid-run refill — only in RUNNING
        # if ps.phase == ProgramPhase.RUNNING:
        #     if mat.current_pot_kg < self.profile.mid_refill_threshold_kg:
        #         self.mid_refill_orchestrator.begin(self.profile)
        #         return

        # Step 3: Gap / dispense events
        # if self.executor.is_busy():
        #     print("[ENGINE] executor busy — skipping this tick")
        #     return
        

        if ps.last_event:
            print(f"[DEBUG] phase={ps.phase} event={ps.last_event}")
            
        event = ps.last_event

        if event is None:
            return

        # if self.executor.is_busy():
        #     print("[ENGINE] executor busy — deferring event")
        #     return

        # 🔴 DO NOT BLOCK DISPENSE ON EXECUTOR BUSY
        if self.executor.is_busy():
            current = getattr(self.executor, "current_command", None)

            if current and current.get("name") in (
                "pot.pressurise",
                "pot.pressurise_stop"
            ):
                print("[ENGINE] executor busy with pressure — allowing dispense")
            else:
                print("[ENGINE] executor busy — IGNORING (dispense priority)")

        # process event
        if event == "pass_enter":
            self._handle_pass_enter(ps)
        elif event == "pass_stable":
            self._handle_pass_stable(ps, machine)
        elif event == "pass_exit":
            self._handle_pass_exit(ps)

        # ✅ CLEAR ONLY AFTER SUCCESSFUL PROCESS
        ps.last_event = None

        # if self.executor.is_busy():
        #     return

    # ──────────────────────────────────────────────────────────────
    # PRESSURE MAINTENANCE
    #
    # Three cases per tick:
    #
    # STOP_SENT (last tick we sent pressurise_stop):
    #   Clear pulse state. Return False — unblock commands.
    #
    # PULSE_ACTIVE (pot_air_in currently open):
    #   Check two stop conditions:
    #     a) Estimated pressure reached pressure_high_mpa → stop
    #     b) Pulse has been open for pressure_top_up_max_s → stop (safety)
    #   Return True — block all other commands.
    #
    # IDLE (no pulse active):
    #   Check cooldown.
    #   If estimated_pressure < pressure_low_mpa → fire pulse.
    #   Return True if pulse just fired, False otherwise.
    #
    # Returns True  → caller must return immediately (command in flight)
    # Returns False → caller may proceed with other commands
    # ──────────────────────────────────────────────────────────────
    def _maintain_pressure(self, now: float, mat) -> bool:

        from app.state.machine_state import machine_state_manager

        machine = machine_state_manager.state

        # 🔴 If gap appears during pulse → force stop
        if machine.gap == 1 and self._pressure_pulse_active:
            from app.commands.helpers import create_and_queue_command

            print("[PRESSURE] Gap detected → stopping pressure immediately")

            create_and_queue_command(name="pot.pressurise_stop", payload={})
            self._pressure_pulse_active = False
            self._pressure_stop_sent = False
            self._pressure_pulse_end_ts = now

            return False

        # 🔴 THIS IS THE MISSING LINE
        if machine.gap == 1:
            return False
        

        if not hasattr(self, "_pressure_last_fire_ts"):
            self._pressure_last_fire_ts = 0

        if not hasattr(self, "_pressure_pulse_end_ts"):
            self._pressure_pulse_end_ts = 0


        from app.state.program_state import program_state
        from app.state.program_state import ProgramPhase

        # 🔴 ADD THIS
        if program_state.phase != ProgramPhase.RUNNING:
            print("[PRESSURE] blocked during line priming")
            return False
            

        from app.commands.helpers import create_and_queue_command

        p = self.profile

        # ── Case 1: stop was sent last tick ──────────────────────
        if self._pressure_stop_sent:
            self._pressure_pulse_active = False
            self._pressure_stop_sent = False
            self._pressure_pulse_end_ts = now
            print(
                f"[PRESSURE_MODEL] Pulse closed — "
                f"estimated={self._estimated_pressure_mpa:.4f} MPa"
            )
            return False

        # ── Case 2: pulse is currently open ──────────────────────
        if self._pressure_pulse_active:
            pulse_elapsed = now - self._pressure_pulse_start_ts
            stop = False
            reason = ""

            if self._estimated_pressure_mpa >= p.pressure_high_mpa:
                stop = True
                reason = f"reached {p.pressure_high_mpa} MPa"
            elif pulse_elapsed >= p.pressure_top_up_max_s:
                stop = True
                reason = f"max pulse time {p.pressure_top_up_max_s}s reached"

            if stop:
                print(
                    f"[PRESSURE_MODEL] Closing pot_air_in — {reason} "
                    f"after {pulse_elapsed:.2f}s"
                )
                create_and_queue_command(name="pot.pressurise_stop", payload={})
                self._pressure_stop_sent = True

            return True   # pulse active — always block

        # ── Case 3: idle — check if top-up needed ────────────────
        if now - self._pressure_pulse_end_ts < p.pressure_top_up_cooldown_s:
            return False

        # if self._estimated_pressure_mpa >= p.pressure_low_mpa:
        #     return False

        # # debounce (VERY IMPORTANT)
        # if now - self._pressure_last_fire_ts < 20.0:
        #     print("[PRESSURE] debounce active — skipping")
        #     return False
        if not hasattr(self, "_pressure_last_fire_ts"):
            self._pressure_last_fire_ts = now
        TOP_UP_INTERVAL = 30.0  # seconds

        if now - self._pressure_last_fire_ts < TOP_UP_INTERVAL:
            return False

        # Pressure below low threshold — fire top-up
        current_kg = mat.current_pot_kg or p.pressure_model_ref_kg
        charge_rate = self._charge_rate_mpa_per_s(current_kg)
        deficit = p.pressure_high_mpa - self._estimated_pressure_mpa
        est_needed_s = deficit / charge_rate if charge_rate > 0 else p.pressure_top_up_max_s

        print(
            f"[PRESSURE_MODEL] Low — "
            f"estimated={self._estimated_pressure_mpa:.4f} MPa "
            f"< low={p.pressure_low_mpa} MPa — "
            f"firing top-up (deficit={deficit:.4f} MPa, "
            f"est {est_needed_s:.1f}s to reach {p.pressure_high_mpa} MPa)"
        )
        # create_and_queue_command(name="pot.pressurise", payload={})


        create_and_queue_command(name="pot.pressurise", payload={})
        self._pressure_last_fire_ts = now

        self._pressure_pulse_active = True
        self._pressure_stop_sent = False
        self._pressure_pulse_start_ts = now
        return True

    # def should_dispense(self, pass_id: int, machine) -> bool:
    #     # only when program is ready/running
    #     # if self.program_state.phase.value not in ("ready", "running"):
    #     #     return False
    #     from app.state.material_state import material_state_manager
    #     from app.state.material_state import material_state_manager

    #     if program_state.phase.value not in ("ready", "running"):
    #         return False


    #     # modulus: every 3rd pass
    #     if (pass_id % self._skip_n) != 0:
    #         return False

    #     # material guards (keep minimal, fast)
    #     # mat = self.material_state

    #     mat = material_state_manager.state

    #     if not mat.line_primed:
    #         return False
        

    #     # if (mat.current_pot_kg or 0.0) <= 0.3:
    #     #     return False

    #     # Weight is NOT used to block dispense
    #     # Only log it for visibility

    #     mat = material_state_manager.state

    #     if mat.current_pot_kg is None:
    #         print("[DISPENSE] weight invalid → allowing dispense")

    #     elif mat.current_pot_kg <= 0.3:
    #         print(f"[DISPENSE] low weight ({mat.current_pot_kg}) → allowing dispense")

    #     # ensure still in gap at decision moment
    #     if machine.gap != 1:
    #         return False

    #     return True

    # def should_dispense(self, pass_id: int, machine) -> bool:
    #     from app.state.program_state import program_state
    #     from app.state.material_state import material_state_manager

    #     mat = material_state_manager.state

    #     # 1. Phase gate
    #     if program_state.phase.value not in ("ready", "running"):
    #         return False

    #     # 2. Modulus gate (every Nth pass)
    #     if (pass_id % self._skip_n) != 0:
    #         return False

    #     # 3. Priming gate (keep this)
    #     if not mat.line_primed:
    #         return False

    #     # 4. Gap confirmation (safety)
    #     # if machine.gap != 1:
    #     #     return False

    #     # 5. Weight → NO LONGER A BLOCKER
    #     if mat.current_pot_kg is None:
    #         print("[DISPENSE] weight invalid → allowing")
    #     else:
    #         print(f"[DISPENSE] weight={mat.current_pot_kg} → allowing")

    #     return True

    def should_dispense(self, pass_id: int, machine) -> bool:
        from app.state.program_state import program_state
        from app.state.material_state import material_state_manager

        mat = material_state_manager.state

        # 1. Phase gate
        if program_state.phase.value not in ("ready", "running"):
            print("[DISPENSE] blocked: phase")
            return False

        # 2. One-shot per gap (CRITICAL)
        if machine.dispense_fired_for_gap:
            print("[DISPENSE] blocked: already fired for this gap")
            return False

        # 3. Modulus gate
        if (pass_id % self._skip_n) != 0:
            print(f"[DISPENSE] blocked: modulus (pid={pass_id})")
            return False

        # 4. Priming gate
        if not mat.line_primed:
            print("[DISPENSE] blocked: not primed")
            return False

        # 5. Gap confirmation (RE-ENABLE THIS)
        if machine.gap != 1:
            print("[DISPENSE] blocked: gap lost")
            return False

        # 6. Weight (non-blocking)
        if mat.current_pot_kg is None:
            print("[DISPENSE] weight invalid → allowing")
        else:
            print(f"[DISPENSE] weight={mat.current_pot_kg} → allowing")

        return True


    # ──────────────────────────────────────────────────────────────
    # PASS EVENTS
    # ──────────────────────────────────────────────────────────────
    def _handle_pass_enter(self, program):
        pid = program.current_pass
        print(f"[PROGRAM_ENGINE] PASS {pid} ENTER")

    def get_dispense_plan(self, pid: int) -> int:
        return self._dispense_ms_for_pass(pid)

    # def _handle_pass_stable(self, program, machine):
    #     pid = program.current_pass
    #     print(f"[PROGRAM_ENGINE] PASS {pid} STABLE")

    def _handle_pass_stable(self, program, machine):

        if machine.gap != 1:
            print("[DISPENSE] skipped: lost gap before execution")
            return

        pid = program.current_pass

        print(f"[PROGRAM_ENGINE] PASS {pid} STABLE")

        if self._pressure_pulse_active:
            print("[DISPENSE] pressure active — ignoring (gap priority)")            

        # 1. Decision
        allowed = self.should_dispense(pid, machine)

        print(
            f"[DISPENSE DECISION] "
            f"pid={pid} allowed={allowed} skip_n={self._skip_n}"
        )

        if not allowed:
            return

        # 2. Plan
        open_ms = self._dispense_ms_for_pass(pid)

        print(f"[DISPENSE] PASS {pid} → firing {open_ms}ms")

        # 3. Execute
        self.executor.send_command({
            "name": "dispense.open",
            "payload": {"open_ms": open_ms}
        })

        # machine.dispense_fired_for_gap = True   # ✅ latch


        # # MODULUS CONTROL
        # if (pid % self._skip_n) != 0:
        #     print(f"[CONTROL] PASS {pid} skipped (skip_n={self._skip_n})")
        #     return

        # print(f"[CONTROL] PASS {pid} → DISPENSE (skip_n={self._skip_n})")
        # if not machine.is_dispense_window():
        #     print(f"[PROGRAM_ENGINE] PASS {pid} not in dispense window — skip")
        #     return

        # open_ms = self._dispense_ms_for_pass(pid)
        # p = program.passes.get(pid)
        # if p:
        #     effective_ms = max(
        #         0,
        #         open_ms - self.profile.nozzle_open_lag_ms - self.profile.nozzle_close_lag_ms
        #     )
        #     p.expected_paint = effective_ms
        #     print(
        #         f"[PROGRAM_ENGINE] PASS {pid} dispense — "
        #         f"solenoid_open_ms={open_ms} "
        #         f"effective_ms={effective_ms} "
        #         f"estimated_pressure={self._estimated_pressure_mpa:.4f} MPa"
        #     )

        # self.executor.send_command({
        #     "name": "dispense.open",
        #     "payload": {"open_ms": open_ms}
        # })

    def _handle_pass_exit(self, program):
        pid = program.current_pass
        print(f"[PROGRAM_ENGINE] PASS {pid} EXIT → DISPENSE STOP")
        # self.executor.send_command({
        #     "name": "dispense.stop",
        #     "payload": {}
        # })

    # ──────────────────────────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────────────────────────
    def _dispense_ms_for_pass(self, pid: int) -> int:
        passes = self.config.get("passes", {})
        pass_cfg = passes.get(str(pid), {})
        if "open_ms" in pass_cfg:
            return int(pass_cfg["open_ms"])
        return self.profile.dispense_open_ms


program_engine = None
