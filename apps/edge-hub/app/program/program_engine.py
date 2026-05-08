# app/program/program_engine.py

import time
from collections import deque

from app.state.program_state import program_state, ProgramPhase
from app.state.material_state import material_state_manager
from app.services.command_executor import CommandExecutor
from app.config.paint_profile import PaintProfile, get_profile, DEFAULT_PROFILE

# ── Pressure constants ─────────────────────────────────────────────────────────
CREDIT_FULL          = 1.0
CREDIT_DISPENSE_COST = 0.10        # per 1000ms open
CREDIT_IDLE_BLEED    = 1.0 / 180.0 # drain to zero in 3 min idle
CREDIT_CHARGE_RATE   = 1.0 / 9.0   # full charge in 9s
CREDIT_LOW_THRESHOLD = 0.35
MIN_SAFE_CREDITS     = 0.15        # skip dispense below this
MAX_PULSE_S          = 12.0
PULSE_COOLDOWN_S     = 30.0
FORCED_INTERVAL_S    = 300.0

# ── Gap classifier constants ───────────────────────────────────────────────────
REST_DWELL_BOOTSTRAP_S = 2.5   # treat gaps held > this as rest until learned
GAP_HISTORY_SIZE       = 20    # rolling window of movement gap durations
REST_RATIO             = 3.0   # rest threshold = median_movement * REST_RATIO


class ProgramEngine:
    """
    Gap-pattern-adaptive dispense engine.

    Pattern: N fast movement gaps → plate rests under sensor → repeat.
    Dispense fires once per REST gap only.
    Pressure runs fully independently — never blocks dispense.
    """

    def __init__(self, executor: CommandExecutor):
        self.executor = executor
        self.config: dict = {}
        self.profile: PaintProfile = DEFAULT_PROFILE
        self._reset_state()

    # ── Full state reset ───────────────────────────────────────────────────────

    def _reset_state(self):
        # Pressure credits
        self._credits: float = 0.0
        self._credits_last_ts: float = time.time()
        self._pulse_active: bool = False
        self._pulse_start_ts: float = 0.0
        self._pulse_end_ts: float = 0.0
        self._last_repressurise_ts: float = time.time()

        # Gap classifier
        self._gap_open_ts: float = 0.0
        self._gap_closed_durations: deque = deque(maxlen=GAP_HISTORY_SIZE)
        self._rest_threshold_s: float = REST_DWELL_BOOTSTRAP_S
        self._prev_gap: int = 0
        self._ready_initialized: bool = False

        # Dispense — one-shot per rest gap
        self._dispense_fired_this_rest: bool = False
        self._last_dispense_open_ms: float | None = None

    # ── Pressure seeding (called by startup_orchestrator) ──────────────────────

    def seed_pressure(self, open_s: float, current_kg: float):
        p = self.profile
        weight_ratio = max(current_kg, 0.05) / p.pressure_model_ref_kg
        charge_rate = CREDIT_CHARGE_RATE * weight_ratio
        self._credits = min(charge_rate * open_s, CREDIT_FULL)
        self._credits_last_ts = time.time()
        self._last_repressurise_ts = time.time()
        self._pulse_end_ts = time.time()
        print(f"[PRESSURE] Seeded credits={self._credits:.3f} (open_s={open_s:.1f}s weight_ratio={weight_ratio:.2f})")

    def on_dispense_complete(self, open_ms: float):
        cost = CREDIT_DISPENSE_COST * (open_ms / 1000.0)
        self._credits = max(0.0, self._credits - cost)
        print(f"[PRESSURE] Dispense cost open_ms={open_ms:.0f} credits={self._credits:.3f}")

    # ── Credit model ───────────────────────────────────────────────────────────

    def _update_credits(self, now: float):
        elapsed = now - self._credits_last_ts
        self._credits_last_ts = now
        if elapsed <= 0:
            return
        if self._pulse_active:
            self._credits += CREDIT_CHARGE_RATE * elapsed
        else:
            self._credits -= CREDIT_IDLE_BLEED * elapsed
        self._credits = max(0.0, min(CREDIT_FULL, self._credits))

    # ── Pressure maintenance — never blocks dispense ───────────────────────────

    def _maintain_pressure(self, now: float, gap: int) -> None:
        from app.commands.helpers import create_and_queue_command

        self._update_credits(now)

        if self._pulse_active:
            elapsed = now - self._pulse_start_ts
            if self._credits >= CREDIT_FULL or elapsed >= MAX_PULSE_S:
                reason = "full" if self._credits >= CREDIT_FULL else "max_time"
                print(f"[PRESSURE] Stop — {reason} elapsed={elapsed:.1f}s credits={self._credits:.3f}")
                create_and_queue_command(name="pot.pressurise_stop", payload={})
                self._pulse_active = False
                self._pulse_end_ts = now
                self._last_repressurise_ts = now
            return  # never start a new pulse while one is running

        # Hard rule: never start pressurise while plate is under sensor
        if gap == 1:
            return

        if now - self._pulse_end_ts < PULSE_COOLDOWN_S:
            return

        credit_low = self._credits < CREDIT_LOW_THRESHOLD
        forced = (now - self._last_repressurise_ts) > FORCED_INTERVAL_S

        if not credit_low and not forced:
            return

        reason = "low" if credit_low else "forced"
        print(f"[PRESSURE] Fire — reason={reason} credits={self._credits:.3f}")
        create_and_queue_command(name="pot.pressurise", payload={})
        self._pulse_active = True
        self._pulse_start_ts = now

    # ── Gap classifier ─────────────────────────────────────────────────────────

    def _update_rest_threshold(self):
        """Recalculate rest threshold from observed movement gap durations."""
        if len(self._gap_closed_durations) < 3:
            return
        sorted_d = sorted(self._gap_closed_durations)
        median = sorted_d[len(sorted_d) // 2]
        if median > 0:
            new_threshold = median * REST_RATIO
            self._rest_threshold_s = new_threshold
            print(f"[GAP_LEARN] median_movement={median:.2f}s rest_threshold={new_threshold:.2f}s")

    def _gap_dwell(self, now: float) -> float:
        if self._gap_open_ts == 0:
            return 0.0
        return now - self._gap_open_ts

    def _is_rest_gap(self, now: float) -> bool:
        return self._gap_dwell(now) >= self._rest_threshold_s

    # ── Program lifecycle ──────────────────────────────────────────────────────

    def start_program(self, config: dict):
        print(f"[PROGRAM_ENGINE] START config={config}")
        self.config = config
        profile_name = config.get("paint_profile")
        self.profile = get_profile(profile_name)
        self._reset_state()

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
        print("[PROGRAM_ENGINE] STOP")
        from app.modes.mode_manager import mode_manager
        from app.modes.mode_types import OperationMode, ProcessMode
        self.executor.send_command({"name": "program.stop", "payload": {}})
        program_state.stop_program()
        mode_manager.set_operation(OperationMode.manual)
        mode_manager.set_process(ProcessMode.idle)

    # ── Main event loop — called every telemetry tick ──────────────────────────

    def on_event(self, machine, program):
        ps = program

        if ps.phase == ProgramPhase.STARTED:
            return

        from app.orchestrators.startup_orchestrator import startup_orchestrator

        if ps.phase in (ProgramPhase.LOADED, ProgramPhase.STARTUP) and not startup_orchestrator.is_started():
            print("[PROGRAM_ENGINE] LOADED → starting startup orchestrator")
            program_state.begin_startup()
            startup_orchestrator.begin(self.profile)
            return

        if ps.phase in (ProgramPhase.PRESSURISING, ProgramPhase.LINE_PRIMING):
            startup_orchestrator.process()
            return

        if ps.phase not in (ProgramPhase.READY, ProgramPhase.RUNNING):
            return

        # ── READY / RUNNING ────────────────────────────────────────────────────
        gap = getattr(machine, "gap", 0)
        now = time.time()

        # One-time init when entering READY
        if ps.phase == ProgramPhase.READY and not self._ready_initialized:
            print("[ENGINE] READY — initialising gap state")
            self._prev_gap = gap
            self._gap_open_ts = now if gap == 1 else 0.0
            self._dispense_fired_this_rest = False
            self._ready_initialized = True

        # Process gap edges
        self._process_gap_edge(gap, now, machine, ps)
        self._prev_gap = gap

        # Pressure runs every tick regardless
        self._maintain_pressure(now, gap)

        # During a confirmed rest gap — attempt dispense on every tick until fired
        if gap == 1 and self._is_rest_gap(now) and not self._dispense_fired_this_rest:
            self._try_dispense(machine, ps, now)

        # Drain legacy event field — prevents old handlers from double-firing
        if ps.last_event:
            ps.last_event = None

    # ── Gap edge processing ────────────────────────────────────────────────────

    def _process_gap_edge(self, gap: int, now: float, machine, program):
        from app.modes.mode_manager import mode_manager
        from app.modes.mode_types import ProcessMode

        if gap == 1 and self._prev_gap == 0:
            # ── Gap opened ────────────────────────────────────────────────────
            self._gap_open_ts = now
            self._dispense_fired_this_rest = False
            self._last_dispense_open_ms = None
            # machine_state resets dispense_fired_for_gap in update_gap() already
            mode_manager.set_process(ProcessMode.window_detected)
            program.new_pass()
            print(f"[GAP] Opened — pass={program.current_pass} threshold={self._rest_threshold_s:.2f}s")

        elif gap == 0 and self._prev_gap == 1:
            # ── Gap closed ────────────────────────────────────────────────────
            if self._gap_open_ts > 0:
                duration = now - self._gap_open_ts
                was_rest = duration >= self._rest_threshold_s
                print(f"[GAP] Closed — duration={duration:.2f}s was_rest={was_rest}")

                # Only movement gaps feed the classifier
                # (rest gaps are outliers — including them skews the median up)
                if not was_rest:
                    self._gap_closed_durations.append(duration)
                    self._update_rest_threshold()

            # Cost accounting for dispense that fired in this gap
            if self._dispense_fired_this_rest and self._last_dispense_open_ms is not None:
                self.on_dispense_complete(self._last_dispense_open_ms)

            self._gap_open_ts = 0.0
            self._dispense_fired_this_rest = False
            self._last_dispense_open_ms = None

            # Reset machine-level flags
            machine.dispense_fired_for_gap = False
            machine.dispense_skipped_for_gap = False
            machine.last_dispense_cmd_id = None

            mode_manager.set_process(ProcessMode.tracking)
            if program.current_pass > 0:
                program.mark_exit(program.current_pass)

    # ── Dispense attempt ───────────────────────────────────────────────────────

    def _try_dispense(self, machine, program, now: float):
        mat = material_state_manager.state
        pid = program.current_pass

        # Phase gate
        if program_state.phase.value not in ("ready", "running"):
            return

        # One-shot per rest gap
        if self._dispense_fired_this_rest:
            return

        # Priming gate
        if not mat.line_primed:
            print("[DISPENSE] blocked: not primed")
            return

        # Pressure safety — skip this rest, pressure recovers during next movement
        if self._credits < MIN_SAFE_CREDITS:
            print(f"[DISPENSE] skipped: low credits={self._credits:.3f}")
            return

        # Don't fire while executor is locked on a non-pressure command
        # (pressure commands are fire-and-forget at hardware level)
        if self._is_busy_for_dispense():
            print(f"[DISPENSE] blocked: executor busy with {self.executor.current_cmd_name}")
            return

        open_ms = self._dispense_ms_for_pass(pid)
        dwell = self._gap_dwell(now)
        print(f"[DISPENSE] PASS {pid} → firing {open_ms}ms (dwell={dwell:.2f}s credits={self._credits:.3f})")

        cmd_id = self.executor.send_command({
            "name": "dispense.open",
            "payload": {"open_ms": open_ms}
        })

        if cmd_id:
            self._dispense_fired_this_rest = True
            self._last_dispense_open_ms = float(open_ms)
            machine.dispense_fired_for_gap = True
            machine.last_dispense_cmd_id = cmd_id

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _is_busy_for_dispense(self) -> bool:
        """Returns True only if executor is locked on something that conflicts with dispense."""
        name = self.executor.current_cmd_name
        if name is None:
            return False
        PRESSURE_CMDS = {"pot.pressurise", "pot.pressurise_stop"}
        return name not in PRESSURE_CMDS

    def _dispense_ms_for_pass(self, pid: int) -> int:
        passes = self.config.get("passes", {})
        pass_cfg = passes.get(str(pid), {})
        if "open_ms" in pass_cfg:
            return int(pass_cfg["open_ms"])
        return self.profile.dispense_open_ms

    # ── Legacy compatibility stubs ─────────────────────────────────────────────
    # These exist so nothing calling them elsewhere crashes

    def should_dispense(self, pass_id: int, machine) -> bool:
        return not self._dispense_fired_this_rest

    def get_dispense_plan(self, pid: int) -> int:
        return self._dispense_ms_for_pass(pid)

    def _handle_pass_enter(self, program): pass
    def _handle_pass_stable(self, program, machine): pass
    def _handle_pass_exit(self, program): pass


program_engine = None

# # app/program/program_engine.py

# # from platform import machine
# import time

# from app.state.program_state import program_state, ProgramPhase
# from app.state.material_state import material_state_manager
# from app.services.command_executor import CommandExecutor
# from app.config.paint_profile import PaintProfile, get_profile, DEFAULT_PROFILE

# # Constants
# CREDIT_FULL            = 1.0
# CREDIT_DISPENSE_COST   = 0.10
# CREDIT_IDLE_BLEED      = 1.0 / 180.0   # full charge gone in 3min idle
# CREDIT_CHARGE_RATE     = 1.0 / 25.0     # 9s = full recharge
# CREDIT_LOW_THRESHOLD = CREDIT_DISPENSE_COST * 2     
# MAX_PULSE_S            = 15.0
# MIN_PULSE_S            = 5.0
# FORCED_INTERVAL_S      = 180.0
# PULSE_COOLDOWN_S       = 3.0
# MAX_DISPENSES_PER_CHARGE = 6
# MIN_SAFE_CREDITS = CREDIT_DISPENSE_COST * 1.3

# class ProgramEngine:
#     """
#     Drives program lifecycle:
#       start_program() → STARTED → LOADED
#           → startup_orchestrator.begin() takes over →
#      PRESSURISING → LINE_PRIMING → READY → RUNNING


#     Pressure model — physical basis:
#       Working range:        0.28 – 0.35 MPa
#       Charge rate:          0.35 MPa / 9s ≈ 0.0389 MPa/s  (full pot)
#       Idle bleed:           0.00117 MPa/s  (solenoid closed, ~5min to zero)
#       Dispense bleed:       0.05 MPa/s    (solenoid open)

#       Derived:
#         Idle: 60s to bleed from 0.35 → 0.28 — top-up fires around 50s idle
#         Dispense: 1.4s to bleed 0.35 → 0.28 during active dispense
#         Top-up from 0.28 → 0.35: ~1.8s of pot_air_in

#     """

#     def __init__(self, executor: CommandExecutor):
#         self.executor = executor
#         self.config: dict = {}
#         self.profile: PaintProfile = DEFAULT_PROFILE
#         self._reset_pressure_state()
#         # self._estimated_pressure_mpa = self.profile.pressure_high_mpa
#         self._ready_initialized = False
#         self._skip_n = 6
#         self._last_weight = None
#         self._window_drop_sum = 0.0
#         self._pass_window = 0
#         self._prev_gap = 0
#         self._target_rate = 1.0 / self._skip_n
#         self._rate_accumulator = 0.0
#         self._dispense_since_last_charge = 0


#     def _reset_pressure_state(self):
#         self._credits: float = 0.0
#         self._credit_charge_rate: float = CREDIT_CHARGE_RATE  # set properly in start_program
#         self._credits_last_ts: float = time.time()
#         self._pulse_active: bool = False
#         self._pulse_start_ts: float = 0.0
#         self._pulse_end_ts: float = 0.0
#         self._last_repressurise_ts: float = 0.0
#         self._pressure_last_fire_ts: float = 0.0   # ADD THIS
#         self._dispense_since_last_charge = 0


#     def seed_pressure(self, open_s: float, current_kg: float):
#         p = self.profile
#         weight_ratio = max(current_kg, 0.05) / p.pressure_model_ref_kg
#         charge_rate = self._credit_charge_rate * weight_ratio
#         self._credits = min(charge_rate * open_s, 1.0)
#         self._credits_last_ts = time.time()
#         self._last_repressurise_ts = time.time()
#         self._pulse_end_ts = time.time()
#         print(f"[PRESSURE] Seeded — open_s={open_s:.1f}s weight_ratio={weight_ratio:.2f} credits={self._credits:.3f}")

#     def on_dispense_complete(self, open_ms: float):
#         BASE_MS = 1000.0
#         cost = CREDIT_DISPENSE_COST * (open_ms / BASE_MS)
#         self._credits = max(0.0, self._credits - cost)

#         print(f"[PRESSURE] Dispense cost — open_ms={open_ms} credits={self._credits:.3f}")
     
#     # ──────────────────────────────────────────────────────────────
#     # API
#     # ──────────────────────────────────────────────────────────────
#     def start_program(self, config: dict):
#         print(f"[PROGRAM_ENGINE] START PROGRAM config={config}")
#         self.config = config
#         self._ready_initialized = False
#         self._rate_accumulator = 0.0        # ← ADD THIS
#         self._last_weight = None
#         self._window_drop_sum = 0.0
#         self._pass_window = 0
#         self._prev_gap = 0
#         profile_name = config.get("paint_profile")
#         self.profile = get_profile(profile_name)
#         self._credit_charge_rate = 1.0 / max(self.profile.pressure_charge_time_s, 1.0)

#         self._reset_pressure_state()

#         from app.orchestrators.startup_orchestrator import startup_orchestrator
#         startup_orchestrator.reset()

#         program_state.start_program()

#         self.executor.send_command({
#             "name": "program.load",
#             "payload": {"program_id": config.get("program_id", "default")}
#         })


#     def _update_credits(self, now: float):
#         elapsed = now - self._credits_last_ts
#         self._credits_last_ts = now

#         # if not self._pulse_active and elapsed > 5.0:
#         #     self._credits *= 0.95

#         if elapsed <= 0:
#             return
#         if self._pulse_active:
#             self._credits += self._credit_charge_rate * elapsed
#         else:
#             self._credits -= CREDIT_IDLE_BLEED * elapsed
#         self._credits = max(0.0, min(CREDIT_FULL, self._credits))

#     def _is_busy_for_dispense(self) -> bool:
#         """
#         Returns True only if executor is locked on something that
#         genuinely conflicts with dispense. Pressure commands don't —
#         they run in parallel at the hardware level.
#         """
#         name = self.executor.current_cmd_name
#         if name is None:
#             return False
#         PRESSURE_CMDS = {"pot.pressurise", "pot.pressurise_stop"}
#         return name not in PRESSURE_CMDS

#     def abort(self, reason: str = None):
#         from app.modes.mode_manager import mode_manager
#         from app.modes.mode_types import OperationMode, ProcessMode
#         program_state.set_phase(ProgramPhase.ABORT, reason or "abort")
#         mode_manager.set_operation(OperationMode.manual)
#         mode_manager.set_process(ProcessMode.idle)



#     def stop_program(self):
#         print("[PROGRAM_ENGINE] STOP PROGRAM")
#         from app.modes.mode_manager import mode_manager
#         from app.modes.mode_types import OperationMode, ProcessMode

#         self.executor.send_command({"name": "program.stop", "payload": {}})
#         program_state.stop_program()

#         mode_manager.set_operation(OperationMode.manual)
#         mode_manager.set_process(ProcessMode.idle)
#         print("[PROGRAM_ENGINE] Modes reset → manual/idle")

#     # ──────────────────────────────────────────────────────────────
#     # Main event loop — called every telemetry tick
#     # ──────────────────────────────────────────────────────────────
#     def on_event(self, machine, program):
#         ps = program
#         mat = material_state_manager.state


#         if ps.phase == ProgramPhase.STARTED:
#             return

#         # 🔴 STARTUP TRIGGER (critical)
#         from app.orchestrators.startup_orchestrator import startup_orchestrator

#         if ps.phase in (ProgramPhase.LOADED, ProgramPhase.STARTUP) and not startup_orchestrator.is_started():
#             from app.orchestrators.startup_orchestrator import startup_orchestrator
#             print("[PROGRAM_ENGINE] LOADED → starting startup orchestrator")
#             program_state.begin_startup()   # 🔴 ADD THIS LINE
#             startup_orchestrator.begin(self.profile)
#             return

#         if ps.phase in (ProgramPhase.PRESSURISING, ProgramPhase.LINE_PRIMING):
#             startup_orchestrator.process()
#             return


#         gap = getattr(machine, "gap", 0)
#         if ps.phase == ProgramPhase.READY and not self._ready_initialized:
#             print("[ENGINE] READY entered — resetting gap state")
#             self._prev_gap = 0
#             self._ready_initialized = True

#         if ps.phase in (ProgramPhase.READY, ProgramPhase.RUNNING):

#             if gap == 1 and self._prev_gap == 0:
#                 # Gap appeared — permit dispense
#                 from app.modes.mode_manager import mode_manager
#                 from app.modes.mode_types import ProcessMode
#                 mode_manager.set_process(ProcessMode.window_detected)
#                 ps.new_pass()

#             elif gap == 1 and self._prev_gap == 1:
#                 if ps.current_pass > 0:
#                     ps.mark_stable(ps.current_pass)

#             elif gap == 0 and self._prev_gap == 1:
#                  # Gap gone — block dispense
#                 from app.modes.mode_manager import mode_manager
#                 from app.modes.mode_types import ProcessMode
#                 mode_manager.set_process(ProcessMode.tracking)
#                 if ps.current_pass > 0:
#                     ps.mark_exit(ps.current_pass)

#         self._prev_gap = gap


#         if ps.phase not in (ProgramPhase.READY, ProgramPhase.RUNNING):
#             return

#         # ── RUNNING / READY ───────────────────────────────────────
#         now = time.time()
#         self._maintain_pressure(now, mat)

        

#         if ps.last_event:
#             print(f"[DEBUG] phase={ps.phase} event={ps.last_event}")
            
#         event = ps.last_event

#         if event is None:
#             return


#         # process event
#         if event == "pass_enter":
#             self._handle_pass_enter(ps)
#         elif event == "pass_stable":
#             self._handle_pass_stable(ps, machine)
#         elif event == "pass_exit":
#             self._handle_pass_exit(ps)

#         # ✅ CLEAR ONLY AFTER SUCCESSFUL PROCESS
#         ps.last_event = None

#         # if self.executor.is_busy():
#         #     return


#     def _maintain_pressure(self, now: float, mat) -> bool:
#         """
#         Never blocks dispense. Just manages pressure independently.
#         Always returns False.
#         """
#         from app.state.machine_state import machine_state_manager
#         from app.commands.helpers import create_and_queue_command

#         machine = machine_state_manager.state

#         self._update_credits(now)

#         # If pulse active — check stop conditions
#         if self._pulse_active:
#             pulse_elapsed = now - self._pulse_start_ts
            
#             # Stop if full OR gap appeared AND we've done minimum time
#             # gap_interrupt = machine.gap == 1 and pulse_elapsed >= MIN_PULSE_S
#             gap_interrupt = False
#             naturally_done = self._credits >= CREDIT_FULL or pulse_elapsed >= MAX_PULSE_S
            
#             if gap_interrupt or naturally_done:
#                 reason = "gap+min_time" if gap_interrupt else ("full" if self._credits >= CREDIT_FULL else "max_time")
#                 self._credits = min(self._credits, 0.92)
#                 print(f"[PRESSURE] Stopping — {reason} elapsed={pulse_elapsed:.1f}s credits={self._credits:.3f}")
#                 create_and_queue_command(name="pot.pressurise_stop", payload={})
#                 self._pulse_active = False
#                 self._pulse_end_ts = now
#                 self._last_repressurise_ts = now
            
#             return False  # NEVER block dispense

#         # Don't start new pulse during gap or cooldown
#         if machine.gap == 1:
#             return False
        
#         if now - self._pulse_end_ts < PULSE_COOLDOWN_S:
#             return False

#         credit_low = self._credits < CREDIT_LOW_THRESHOLD
#         forced = (now - self._last_repressurise_ts) > FORCED_INTERVAL_S

#         if not credit_low and not forced:
#             return False

#         deficit = CREDIT_FULL - self._credits
#         pulse_s = max(MIN_PULSE_S, min(deficit / CREDIT_CHARGE_RATE, MAX_PULSE_S))
#         reason = "low" if credit_low else "forced"
#         print(f"[PRESSURE] Firing — reason={reason} credits={self._credits:.3f} pulse={pulse_s:.1f}s")

#         create_and_queue_command(name="pot.pressurise", payload={})
#         self._pulse_active = True
#         self._pulse_start_ts = now
#         return False  # NEVER block dispense


#     def should_dispense(self, pass_id: int, machine) -> bool:
#         from app.state.program_state import program_state
#         from app.state.material_state import material_state_manager

#         mat = material_state_manager.state

#         # 1. Phase gate
#         if program_state.phase.value not in ("ready", "running"):
#             print("[DISPENSE] blocked: phase")
#             return False

#         # 2. One-shot per gap (CRITICAL)
#         if machine.dispense_fired_for_gap:
#             print("[DISPENSE] blocked: already fired for this gap")
#             return False


#         # 4. Priming gate
#         if not mat.line_primed:
#             print("[DISPENSE] blocked: not primed")
#             return False

#         # 5. Gap confirmation (RE-ENABLE THIS)
#         if machine.gap != 1:
#             print("[DISPENSE] blocked: gap lost")
#             return False

#         # 6. Weight (non-blocking)
#         if mat.current_pot_kg is None:
#             print("[DISPENSE] weight invalid → allowing")
#         else:
#             print(f"[DISPENSE] weight={mat.current_pot_kg} → allowing")

#         return True

#     def _force_repressurise(self, now: float):
#         from app.commands.helpers import create_and_queue_command

#         print(f"[PRESSURE] FORCE RECHARGE — credits={self._credits:.3f}")

#         create_and_queue_command(name="pot.pressurise", payload={})

#         self._pulse_active = True
#         self._pulse_start_ts = now
#         self._last_repressurise_ts = now   # ✅ ADD THIS
#         self._dispense_since_last_charge = 0   # reset counter


#     # ──────────────────────────────────────────────────────────────
#     # PASS EVENTS
#     # ──────────────────────────────────────────────────────────────
#     def _handle_pass_enter(self, program):
#         pid = program.current_pass
#         print(f"[PROGRAM_ENGINE] PASS {pid} ENTER")

#         # ✅ ADD THIS
#         self._rate_accumulator += self._target_rate
#         self._rate_accumulator = min(self._rate_accumulator, 2.0)

#         print(f"[RATE] acc={self._rate_accumulator:.2f}")

#     def get_dispense_plan(self, pid: int) -> int:
#         return self._dispense_ms_for_pass(pid)


#     def _handle_pass_stable(self, program, machine):
#         pid = program.current_pass
#         now = time.time()

#         if machine.dispense_fired_for_gap:
#             return
        
#         if self._pulse_active:
#             print("[DISPENSE] blocked: recharge in progress")
#             return

#         # 🔴 RATE ACCUMULATION (THIS IS THE NEW CORE)

#         print(f"[RATE] acc={self._rate_accumulator:.2f}")

#         if machine.gap != 1:
#             print("[DISPENSE] skipped: lost gap before execution")
#             return

#         #     return

#         if self._is_busy_for_dispense():
#             print(f"[DISPENSE] PASS {pid} SKIPPED (executor busy with non-pressure cmd)")
#             return

#         print(f"[PROGRAM_ENGINE] PASS {pid} STABLE")

#         # 🔴 BASE GATING (phase, priming, gap, one-shot)
#         if not self.should_dispense(pid, machine):
#             return

#         if self._rate_accumulator < 1.0:
#             return

#         # 2. Plan
#         open_ms = self._dispense_ms_for_pass(pid)

#         if self._dispense_since_last_charge >= MAX_DISPENSES_PER_CHARGE:
#             if not self._pulse_active:
#                 print("[PRESSURE] periodic reset — forcing recharge")
#                 self._force_repressurise(now)
#             return


#         if self._credits < MIN_SAFE_CREDITS:
#             if not self._pulse_active:
#                 print("[DISPENSE] forcing repressurise before dispense")
#                 self._force_repressurise(now)
#             return
        

#         print(f"[DISPENSE] PASS {pid} → firing {open_ms}ms")


#         cmd_id = self.executor.send_command({
#             "name": "dispense.open",
#             "payload": {"open_ms": open_ms}
#         })

#         if cmd_id:
#             self._rate_accumulator -= 1.0
#             machine.dispense_fired_for_gap = True    
#             machine.dispense_skipped_for_gap = False
#             machine.last_dispense_cmd_id = cmd_id
#             machine.last_dispense_open_ms = open_ms
#             self._dispense_since_last_charge += 1   # ✅ increment ONLY after actual fire



#     def _handle_pass_exit(self, program):
#         pid = program.current_pass
#         print(f"[PROGRAM_ENGINE] PASS {pid} EXIT → DISPENSE STOP")

#         from app.state.machine_state import machine_state_manager
#         machine = machine_state_manager.state

#         if machine.dispense_fired_for_gap and machine.last_dispense_open_ms is not None:
#             self.on_dispense_complete(machine.last_dispense_open_ms)

#         # 🔴 RESET FOR NEXT GAP
#         machine.last_dispense_open_ms = None
#         machine.dispense_fired_for_gap = False
#         machine.dispense_skipped_for_gap = False   # 🔴 ADD THIS
#         machine.last_dispense_cmd_id = None
#         # self.executor.send_command({
#         #     "name": "dispense.stop",
#         #     "payload": {}
#         # })

#     # ──────────────────────────────────────────────────────────────
#     # Helpers
#     # ──────────────────────────────────────────────────────────────
#     def _dispense_ms_for_pass(self, pid: int) -> int:
#         passes = self.config.get("passes", {})
#         pass_cfg = passes.get(str(pid), {})
#         if "open_ms" in pass_cfg:
#             return int(pass_cfg["open_ms"])
#         return self.profile.dispense_open_ms


# program_engine = None
