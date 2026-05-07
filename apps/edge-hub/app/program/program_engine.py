# app/program/program_engine.py

# from platform import machine
import time

from app.state.program_state import program_state, ProgramPhase
from app.state.material_state import material_state_manager
from app.services.command_executor import CommandExecutor
from app.config.paint_profile import PaintProfile, get_profile, DEFAULT_PROFILE

# Constants
CREDIT_FULL            = 1.0
CREDIT_DISPENSE_COST   = 0.10
CREDIT_IDLE_BLEED      = 1.0 / 180.0   # full charge gone in 3min idle
CREDIT_CHARGE_RATE     = 1.0 / 25.0     # 9s = full recharge
CREDIT_LOW_THRESHOLD = CREDIT_DISPENSE_COST * 2     
MAX_PULSE_S            = 15.0
MIN_PULSE_S            = 5.0
FORCED_INTERVAL_S      = 180.0
PULSE_COOLDOWN_S       = 3.0
MAX_DISPENSES_PER_CHARGE = 6
MIN_SAFE_CREDITS = CREDIT_DISPENSE_COST * 1.3

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
        # self._estimated_pressure_mpa = self.profile.pressure_high_mpa
        self._ready_initialized = False
        self._skip_n = 6
        self._last_weight = None
        self._window_drop_sum = 0.0
        self._pass_window = 0
        self._prev_gap = 0
        self._target_rate = 1.0 / self._skip_n
        self._rate_accumulator = 0.0
        self._dispense_since_last_charge = 0
    # ──────────────────────────────────────────────────────────────
    # Pressure model state
    # ──────────────────────────────────────────────────────────────
    # def _reset_pressure_state(self):
    #     # Estimated pot pressure in MPa — the single number we track
    #     self._estimated_pressure_mpa: float = 0.0

    #     # Timestamp of last model update (used to compute elapsed per tick)
    #     self._pressure_last_ts: float = time.time()

    #     # True while pot_air_in is open for a top-up pulse
    #     self._pressure_pulse_active: bool = False

    #     # Timestamp when current pulse opened
    #     self._pressure_pulse_start_ts: float = 0.0

    #     # True after pressurise_stop sent — clear next tick
    #     self._pressure_stop_sent: bool = False

    #     # Timestamp when last pulse completed (for cooldown)
    #     self._pressure_pulse_end_ts: float = 0.0
    #     self._pressure_fallback_ts: float = 0.0


    def _reset_pressure_state(self):
        self._credits: float = 0.0
        self._credits_last_ts: float = time.time()
        self._pulse_active: bool = False
        self._pulse_start_ts: float = 0.0
        self._pulse_end_ts: float = 0.0
        self._last_repressurise_ts: float = 0.0
        self._pressure_last_fire_ts: float = 0.0   # ADD THIS
        self._dispense_since_last_charge = 0



    # def seed_pressure(self, open_s: float, current_kg: float):
    #     """
    #     Called after any pot_air_in open event (startup pressurise,
    #     mid-refill repressurise) so the model starts accurately.

    #     Computes how much pressure was built by that open duration,
    #     accounting for current paint weight (headspace).
    #     """
    #     p = self.profile
    #     charge_rate = self._charge_rate_mpa_per_s(current_kg)
    #     gained = charge_rate * open_s
    #     self._estimated_pressure_mpa = min(
    #         self._estimated_pressure_mpa + gained,
    #         p.pressure_high_mpa
    #     )
    #     self._pressure_last_ts = time.time()
    #     print(
    #         f"[PRESSURE_MODEL] Seeded — open_s={open_s:.1f}s "
    #         f"charge_rate={charge_rate:.5f} MPa/s "
    #         f"gained={gained:.4f} MPa "
    #         f"estimated={self._estimated_pressure_mpa:.4f} MPa"
    #     )

    def seed_pressure(self, open_s: float, current_kg: float):
        p = self.profile
        weight_ratio = max(current_kg, 0.05) / p.pressure_model_ref_kg
        charge_rate = (1.0 / 9.0) * weight_ratio
         # Startup pressurise is always a full charge — seed at least 0.8
        # self._credits = max(min(charge_rate * open_s, 1.0), 0.8)
        self._credits = min(charge_rate * open_s, 1.0)
        self._credits_last_ts = time.time()
        self._last_repressurise_ts = time.time()
        self._pulse_end_ts = time.time()
        print(f"[PRESSURE] Seeded — open_s={open_s:.1f}s weight_ratio={weight_ratio:.2f} credits={self._credits:.3f}")

    def on_dispense_complete(self, open_ms: float):
        BASE_MS = 1000.0
        cost = CREDIT_DISPENSE_COST * (open_ms / BASE_MS)
        self._credits = max(0.0, self._credits - cost)

        print(f"[PRESSURE] Dispense cost — open_ms={open_ms} credits={self._credits:.3f}")
        
    # def _charge_rate_mpa_per_s(self, current_kg: float) -> float:
    #     """
    #     How fast pot pressurises at current fill weight.
    #     More paint = less headspace = faster charge.
    #     charge_rate = (pressure_high / charge_time_s) * (current_kg / ref_kg) * factor
    #     """
    #     p = self.profile
    #     if current_kg <= 0:
    #         current_kg = p.pressure_model_ref_kg
    #     base_rate = p.pressure_high_mpa / p.pressure_charge_time_s
    #     weight_ratio = current_kg / p.pressure_model_ref_kg
    #     return base_rate * weight_ratio * p.pressure_model_headspace_factor

    # def _update_pressure_model(self, now: float, dispensing_active: bool):
    #     """
    #     Tick the pressure model:
    #       - Apply bleed (idle or dispense rate) for elapsed time
    #       - If pulse active, apply charge for elapsed time
    #       - Clamp to [0, pressure_high_mpa]
    #     """
    #     p = self.profile
    #     mat = material_state_manager.state
    #     elapsed = now - self._pressure_last_ts
    #     self._pressure_last_ts = now

    #     if elapsed <= 0:
    #         return

    #     # # Apply bleed
    #     # if dispensing_active:
    #     #     bleed = p.pressure_dispense_bleed_mpa_per_s * elapsed
    #     # else:
    #     #     bleed = p.pressure_idle_bleed_mpa_per_s * elapsed

    #     # REPLACE with:
    #     # Freeze model if sensor is dead — don't decay to zero
    #     from app.state.machine_state import machine_state_manager
    #     pot_pressure = getattr(machine_state_manager.state, "pot_pressure", -1.0)
    #     if pot_pressure is None or pot_pressure <= 0.0:
    #         return

    #     # Apply bleed
    #     if dispensing_active:
    #         bleed = p.pressure_dispense_bleed_mpa_per_s * elapsed
    #     else:
    #         bleed = p.pressure_idle_bleed_mpa_per_s * elapsed

    #     self._estimated_pressure_mpa = max(
    #         0.0,
    #         self._estimated_pressure_mpa - bleed
    #     )

    #     # Apply charge if pot_air_in open
    #     if self._pressure_pulse_active:
    #         current_kg = mat.current_pot_kg or p.pressure_model_ref_kg
    #         charge = self._charge_rate_mpa_per_s(current_kg) * elapsed
    #         self._estimated_pressure_mpa = min(
    #             self._estimated_pressure_mpa + charge,
    #             p.pressure_high_mpa
    #         )

    # ──────────────────────────────────────────────────────────────
    # API
    # ──────────────────────────────────────────────────────────────
    def start_program(self, config: dict):
        print(f"[PROGRAM_ENGINE] START PROGRAM config={config}")
        self.config = config
        self._ready_initialized = False
        self._rate_accumulator = 0.0        # ← ADD THIS
        self._last_weight = None
        self._window_drop_sum = 0.0
        self._pass_window = 0
        self._prev_gap = 0
        profile_name = config.get("paint_profile")
        self.profile = get_profile(profile_name)

        # self.mid_refill_orchestrator.reset()
        self._reset_pressure_state()
        # self._pressure_last_fire_ts = time.time()   # 🔴 ADD THIS

        # self._estimated_pressure_mpa = self.profile.pressure_high_mpa
        # self._pressure_last_fire_ts = time.time()   # 🔴 ADD THIS

        from app.orchestrators.startup_orchestrator import startup_orchestrator
        startup_orchestrator.reset()

        program_state.start_program()

        self.executor.send_command({
            "name": "program.load",
            "payload": {"program_id": config.get("program_id", "default")}
        })


    # def _update_credits(self, now: float):
    #     elapsed = now - self._credits_last_ts
    #     self._credits_last_ts = now
    #     if elapsed <= 0:
    #         return
    #     if self._pulse_active:
    #         from app.state.machine_state import machine_state_manager
    #         pot_air_in = getattr(machine_state_manager.state, "pot_air_in", False)
    #         if pot_air_in:
    #             self._credits += CREDIT_CHARGE_RATE * elapsed   # was self.CREDIT_CHARGE_RATE
    #         else:
    #             self._pulse_active = False
    #             self._pulse_end_ts = now
    #     else:
    #         self._credits -= CREDIT_IDLE_BLEED * elapsed
    #     self._credits = max(0.0, min(CREDIT_FULL, self._credits))


    def _update_credits(self, now: float):
        elapsed = now - self._credits_last_ts
        self._credits_last_ts = now

        # if not self._pulse_active and elapsed > 5.0:
        #     self._credits *= 0.95

        if elapsed <= 0:
            return
        if self._pulse_active:
            self._credits += CREDIT_CHARGE_RATE * elapsed
        else:
            self._credits -= CREDIT_IDLE_BLEED * elapsed
        self._credits = max(0.0, min(CREDIT_FULL, self._credits))

    def _is_busy_for_dispense(self) -> bool:
        """
        Returns True only if executor is locked on something that
        genuinely conflicts with dispense. Pressure commands don't —
        they run in parallel at the hardware level.
        """
        name = self.executor.current_cmd_name
        if name is None:
            return False
        PRESSURE_CMDS = {"pot.pressurise", "pot.pressurise_stop"}
        return name not in PRESSURE_CMDS

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

   # ← ADD HERE
        if ps.phase in (ProgramPhase.PRESSURISING, ProgramPhase.LINE_PRIMING):
            startup_orchestrator.process()
            return


        gap = getattr(machine, "gap", 0)
        if ps.phase == ProgramPhase.READY and not self._ready_initialized:
            print("[ENGINE] READY entered — resetting gap state")
            self._prev_gap = 0
            self._ready_initialized = True

        # if not hasattr(self, "_prev_gap"):
        #     self._prev_gap = 0

        if ps.phase in (ProgramPhase.READY, ProgramPhase.RUNNING):

            if gap == 1 and self._prev_gap == 0:
                # Gap appeared — permit dispense
                from app.modes.mode_manager import mode_manager
                from app.modes.mode_types import ProcessMode
                mode_manager.set_process(ProcessMode.window_detected)
                ps.new_pass()

            elif gap == 1 and self._prev_gap == 1:
                if ps.current_pass > 0:
                    ps.mark_stable(ps.current_pass)

            elif gap == 0 and self._prev_gap == 1:
                 # Gap gone — block dispense
                from app.modes.mode_manager import mode_manager
                from app.modes.mode_types import ProcessMode
                mode_manager.set_process(ProcessMode.tracking)
                if ps.current_pass > 0:
                    ps.mark_exit(ps.current_pass)

        self._prev_gap = gap


        if ps.phase not in (ProgramPhase.READY, ProgramPhase.RUNNING):
            return

        # ── RUNNING / READY ───────────────────────────────────────
        now = time.time()

        # Tick pressure model — must happen every tick regardless
        # dispensing_active = getattr(mat, "dispensing_active", False)

        # if ps.phase in (ProgramPhase.RUNNING, ProgramPhase.READY):
        #     self._update_pressure_model(now, dispensing_active)
        # self._update_pressure_model(now, dispensing_active)

        # credits updated inside _maintain_pressure each tick


        # Step 1: Pressure maintenance — returns True if pot_air_in
        # is open or a command was just sent. Block everything else.
        # if self._maintain_pressure(now, mat):
        #     return
        self._maintain_pressure(now, mat)
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
        # if self.executor.is_busy():
        #     current = getattr(self.executor, "current_command", None)

        #     if current and current.get("name") in (
        #         "pot.pressurise",
        #         "pot.pressurise_stop"
        #     ):
        #         print("[ENGINE] executor busy with pressure — allowing dispense")
        #     else:
        #         print("[ENGINE] executor busy — IGNORING (dispense priority)")

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
    # def _maintain_pressure(self, now: float, mat) -> bool:

    #     from app.state.machine_state import machine_state_manager

    #     machine = machine_state_manager.state

    #     # 🔴 If gap appears during pulse → force stop
    #     if machine.gap == 1 and self._pressure_pulse_active:
    #         from app.commands.helpers import create_and_queue_command

    #         print("[PRESSURE] Gap detected → stopping pressure immediately")

    #         create_and_queue_command(name="pot.pressurise_stop", payload={})
    #         self._pressure_pulse_active = False
    #         self._pressure_stop_sent = False
    #         self._pressure_pulse_end_ts = now

    #         return False

    #     # 🔴 THIS IS THE MISSING LINE
    #     if machine.gap == 1:
    #         return False
        

    #     if not hasattr(self, "_pressure_last_fire_ts"):
    #         self._pressure_last_fire_ts = 0

    #     if not hasattr(self, "_pressure_pulse_end_ts"):
    #         self._pressure_pulse_end_ts = 0


    #     from app.state.program_state import program_state
    #     from app.state.program_state import ProgramPhase

    #     # 🔴 ADD THIS
    #     if program_state.phase not in (ProgramPhase.RUNNING, ProgramPhase.READY):
    #         print("[PRESSURE] blocked during line priming")
    #         return False

    #     from app.commands.helpers import create_and_queue_command

    #     p = self.profile

    #     # ── Case 1: stop was sent last tick ──────────────────────
    #     if self._pressure_stop_sent:
    #         self._pressure_pulse_active = False
    #         self._pressure_stop_sent = False
    #         self._pressure_pulse_end_ts = now
    #         print(
    #             f"[PRESSURE_MODEL] Pulse closed — "
    #             f"estimated={self._estimated_pressure_mpa:.4f} MPa"
    #         )
    #         return False

    #     # ── Case 2: pulse is currently open ──────────────────────
    #     if self._pressure_pulse_active:
    #         pulse_elapsed = now - self._pressure_pulse_start_ts
    #         stop = False
    #         reason = ""

    #         if self._estimated_pressure_mpa >= p.pressure_high_mpa:
    #             stop = True
    #             reason = f"reached {p.pressure_high_mpa} MPa"
    #         elif pulse_elapsed >= p.pressure_top_up_max_s:
    #             stop = True
    #             reason = f"max pulse time {p.pressure_top_up_max_s}s reached"

    #         if stop:
    #             print(
    #                 f"[PRESSURE_MODEL] Closing pot_air_in — {reason} "
    #                 f"after {pulse_elapsed:.2f}s"
    #             )
    #             create_and_queue_command(name="pot.pressurise_stop", payload={})
    #             self._pressure_stop_sent = True

    #         return False   # pulse active — always block

    #     # ── Case 3: idle — check if top-up needed ────────────────
    #     if now - self._pressure_pulse_end_ts < p.pressure_top_up_cooldown_s:
    #         return False

    #     if self._estimated_pressure_mpa >= p.pressure_low_mpa:
    #         return False

    #     # ── NEW: 3 lines to kill the spam ────────────────────────
    #     FALLBACK_COOLDOWN_S = 15.0
    #     # if not hasattr(self, "_pressure_fallback_ts"):
    #     #     self._pressure_fallback_ts = 0.0

    #     pot_pressure = getattr(machine_state_manager.state, "pot_pressure", -1.0)
    #     sensor_dead = pot_pressure is None or pot_pressure <= 0.0

    #     if sensor_dead:
    #         if now - self._pressure_fallback_ts < FALLBACK_COOLDOWN_S:
    #             return False   # ← this is the only line that matters
    #         self._pressure_fallback_ts = now
    #         print(f"[PRESSURE_MODEL] Sensor invalid ({pot_pressure}) — fallback pulse (15s cooldown)")



    #     # # debounce (VERY IMPORTANT)
    #     # if now - self._pressure_last_fire_ts < 20.0:
    #     #     print("[PRESSURE] debounce active — skipping")
    #     # #     return False
    #     # if not hasattr(self, "_pressure_last_fire_ts"):
    #     #     self._pressure_last_fire_ts = now
    #     # TOP_UP_INTERVAL = 30.0  # seconds

    #     # if now - self._pressure_last_fire_ts < TOP_UP_INTERVAL:
    #     #     return False

    #     # Pressure below low threshold — fire top-up
    #     current_kg = mat.current_pot_kg or p.pressure_model_ref_kg
    #     charge_rate = self._charge_rate_mpa_per_s(current_kg)
    #     deficit = p.pressure_high_mpa - self._estimated_pressure_mpa
    #     est_needed_s = deficit / charge_rate if charge_rate > 0 else p.pressure_top_up_max_s

    #     print(
    #         f"[PRESSURE_MODEL] Low — "
    #         f"estimated={self._estimated_pressure_mpa:.4f} MPa "
    #         f"< low={p.pressure_low_mpa} MPa — "
    #         f"firing top-up (deficit={deficit:.4f} MPa, "
    #         f"est {est_needed_s:.1f}s to reach {p.pressure_high_mpa} MPa)"
    #     )
    #     # create_and_queue_command(name="pot.pressurise", payload={})


    #     create_and_queue_command(name="pot.pressurise", payload={})
    #     self._pressure_last_fire_ts = now

    #     self._pressure_pulse_active = True
    #     self._pressure_stop_sent = False
    #     self._pressure_pulse_start_ts = now
    #     return False
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

#  problem : pressurise is stopped by gap appearance
    # def _maintain_pressure(self, now: float, mat) -> bool:
    #     from app.state.machine_state import machine_state_manager
    #     from app.commands.helpers import create_and_queue_command

    #     machine = machine_state_manager.state

    #     # Stop pulse immediately if gap opens
    #     if machine.gap == 1 and self._pulse_active:
    #         print("[PRESSURE] Gap during pulse — stopping")
    #         create_and_queue_command(name="pot.pressurise_stop", payload={})
    #         self._pulse_active = False
    #         self._pulse_end_ts = now
    #         return False

    #     # Never repressurise during gap
    #     if machine.gap == 1:
    #         return False

    #     self._update_credits(now)

    #     # Pulse active — check stop conditions
    #     if self._pulse_active:
    #         pulse_elapsed = now - self._pulse_start_ts
    #         if self._credits >= CREDIT_FULL or pulse_elapsed >= MAX_PULSE_S:
    #             reason = "full" if self._credits >= CREDIT_FULL else "max_time"
    #             print(f"[PRESSURE] Stopping pulse — {reason} credits={self._credits:.3f}")
    #             create_and_queue_command(name="pot.pressurise_stop", payload={})
    #             self._pulse_active = False
    #             self._pulse_end_ts = now
    #             self._last_repressurise_ts = now
    #         return True  # block dispense while pulsing

    #     # Cooldown
    #     if now - self._pulse_end_ts < PULSE_COOLDOWN_S:
    #         return False

    #     # Fire conditions
    #     credit_low = self._credits < CREDIT_LOW_THRESHOLD
    #     forced = (now - self._last_repressurise_ts) > FORCED_INTERVAL_S

    #     if not credit_low and not forced:
    #         return False

    #     deficit = CREDIT_FULL - self._credits
    #     pulse_s = max(MIN_PULSE_S, min(deficit / CREDIT_CHARGE_RATE, MAX_PULSE_S))
    #     reason = "low" if credit_low else "forced"
    #     print(f"[PRESSURE] Firing — reason={reason} credits={self._credits:.3f} pulse={pulse_s:.1f}s")

    #     create_and_queue_command(name="pot.pressurise", payload={})
    #     self._pulse_active = True
    #     self._pulse_start_ts = now
    #     return True

    # def _maintain_pressure(self, now: float, mat) -> bool:
    #     from app.state.machine_state import machine_state_manager
    #     from app.commands.helpers import create_and_queue_command

    #     machine = machine_state_manager.state

    #     # Stop pulse only if gap AND we're about to dispense (credits sufficient)
    #     # Don't stop just because gap appeared — let it build up
    #     if machine.gap == 1 and self._pulse_active:
    #         # Only stop if we have enough credits to potentially dispense
    #         if self._credits >= CREDIT_LOW_THRESHOLD:
    #             print("[PRESSURE] Gap during pulse — stopping (credits sufficient)")
    #             create_and_queue_command(name="pot.pressurise_stop", payload={})
    #             self._pulse_active = False
    #             self._pulse_end_ts = now
    #         # else: keep pulsing through the gap to build credits
    #         return False

    #     # Never START a new repressurise pulse during gap
    #     if machine.gap == 1:
    #         self._update_credits(now)
    #         return False

    #     self._update_credits(now)

    #     # Pulse active — check stop conditions
    #     if self._pulse_active:
    #         pulse_elapsed = now - self._pulse_start_ts
    #         if self._credits >= CREDIT_FULL or pulse_elapsed >= MAX_PULSE_S:
    #             reason = "full" if self._credits >= CREDIT_FULL else "max_time"
    #             print(f"[PRESSURE] Stopping pulse — {reason} credits={self._credits:.3f}")
    #             create_and_queue_command(name="pot.pressurise_stop", payload={})
    #             self._pulse_active = False
    #             self._pulse_end_ts = now
    #             self._last_repressurise_ts = now
    #         return True  # block dispense while pulsing

    #     # Cooldown
    #     if now - self._pulse_end_ts < PULSE_COOLDOWN_S:
    #         return False

    #     # Fire conditions
    #     credit_low = self._credits < CREDIT_LOW_THRESHOLD
    #     forced = (now - self._last_repressurise_ts) > FORCED_INTERVAL_S

    #     if not credit_low and not forced:
    #         return False

    #     deficit = CREDIT_FULL - self._credits
    #     pulse_s = max(MIN_PULSE_S, min(deficit / CREDIT_CHARGE_RATE, MAX_PULSE_S))
    #     reason = "low" if credit_low else "forced"
    #     print(f"[PRESSURE] Firing — reason={reason} credits={self._credits:.3f} pulse={pulse_s:.1f}s")

    #     create_and_queue_command(name="pot.pressurise", payload={})
    #     self._pulse_active = True
    #     self._pulse_start_ts = now
    #     return True


    def _maintain_pressure(self, now: float, mat) -> bool:
        """
        Never blocks dispense. Just manages pressure independently.
        Always returns False.
        """
        from app.state.machine_state import machine_state_manager
        from app.commands.helpers import create_and_queue_command

        machine = machine_state_manager.state

        self._update_credits(now)

        # If pulse active — check stop conditions
        if self._pulse_active:
            pulse_elapsed = now - self._pulse_start_ts
            
            # Stop if full OR gap appeared AND we've done minimum time
            # gap_interrupt = machine.gap == 1 and pulse_elapsed >= MIN_PULSE_S
            gap_interrupt = False
            naturally_done = self._credits >= CREDIT_FULL or pulse_elapsed >= MAX_PULSE_S
            
            if gap_interrupt or naturally_done:
                reason = "gap+min_time" if gap_interrupt else ("full" if self._credits >= CREDIT_FULL else "max_time")
                self._credits = min(self._credits, 0.92)
                print(f"[PRESSURE] Stopping — {reason} elapsed={pulse_elapsed:.1f}s credits={self._credits:.3f}")
                create_and_queue_command(name="pot.pressurise_stop", payload={})
                self._pulse_active = False
                self._pulse_end_ts = now
                self._last_repressurise_ts = now
            
            return False  # NEVER block dispense

        # Don't start new pulse during gap or cooldown
        if machine.gap == 1:
            return False
        
        if now - self._pulse_end_ts < PULSE_COOLDOWN_S:
            return False

        # if now - self._last_repressurise_ts > 300:  # 5 minutes
        #     if not self._pulse_active:
        #         print("[PRESSURE] periodic time reset")
        #         self._force_repressurise(now)       
        #         return False# ← ADD THIS



        # Fire conditions
        credit_low = self._credits < CREDIT_LOW_THRESHOLD
        forced = (now - self._last_repressurise_ts) > FORCED_INTERVAL_S

        if not credit_low and not forced:
            return False

        deficit = CREDIT_FULL - self._credits
        pulse_s = max(MIN_PULSE_S, min(deficit / CREDIT_CHARGE_RATE, MAX_PULSE_S))
        reason = "low" if credit_low else "forced"
        print(f"[PRESSURE] Firing — reason={reason} credits={self._credits:.3f} pulse={pulse_s:.1f}s")

        create_and_queue_command(name="pot.pressurise", payload={})
        self._pulse_active = True
        self._pulse_start_ts = now
        return False  # NEVER block dispense





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

        # # 3. Modulus gate
        # if (pass_id % self._skip_n) != 0:
        #     print(f"[DISPENSE] blocked: modulus (pid={pass_id})")
        #     return False

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

    def _force_repressurise(self, now: float):
        from app.commands.helpers import create_and_queue_command

        print(f"[PRESSURE] FORCE RECHARGE — credits={self._credits:.3f}")

        create_and_queue_command(name="pot.pressurise", payload={})

        self._pulse_active = True
        self._pulse_start_ts = now
        self._last_repressurise_ts = now   # ✅ ADD THIS
        self._dispense_since_last_charge = 0   # reset counter


    # ──────────────────────────────────────────────────────────────
    # PASS EVENTS
    # ──────────────────────────────────────────────────────────────
    def _handle_pass_enter(self, program):
        pid = program.current_pass
        print(f"[PROGRAM_ENGINE] PASS {pid} ENTER")

        # ✅ ADD THIS
        self._rate_accumulator += self._target_rate
        self._rate_accumulator = min(self._rate_accumulator, 2.0)

        print(f"[RATE] acc={self._rate_accumulator:.2f}")

    def get_dispense_plan(self, pid: int) -> int:
        return self._dispense_ms_for_pass(pid)

    # def _handle_pass_stable(self, program, machine):
    #     pid = program.current_pass
    #     print(f"[PROGRAM_ENGINE] PASS {pid} STABLE")

    def _handle_pass_stable(self, program, machine):
        pid = program.current_pass
        now = time.time()

        if machine.dispense_fired_for_gap:
            return
        
        if self._pulse_active:
            print("[DISPENSE] blocked: recharge in progress")
            return

        # 🔴 RATE ACCUMULATION (THIS IS THE NEW CORE)

        print(f"[RATE] acc={self._rate_accumulator:.2f}")

        if machine.gap != 1:
            print("[DISPENSE] skipped: lost gap before execution")
            return

        # if self._pressure_pulse_active:
        #     print("[DISPENSE] pressure active — ignoring (gap priority)")
            # return    

        # if self._pulse_active:
        #     print("[DISPENSE] pulse active — ignoring (gap priority)")
        #     return

        # if self.executor.is_busy():
        #     print(f"[DISPENSE] PASS {pid} SKIPPED (executor busy)")
        #     return

        if self._is_busy_for_dispense():
            print(f"[DISPENSE] PASS {pid} SKIPPED (executor busy with non-pressure cmd)")
            return

            # machine.dispense_fired_for_gap = True   # mark as consumed
            # machine.dispense_skipped_for_gap = True # <-- NEW FLAG


        print(f"[PROGRAM_ENGINE] PASS {pid} STABLE")     

        # 🔴 BASE GATING (phase, priming, gap, one-shot)
        if not self.should_dispense(pid, machine):
            return

        if self._rate_accumulator < 1.0:
            return
        # 1. Decision
        # allowed = self.should_dispense(pid, machine)
        # self._rate_accumulator += self._target_rate

        # 2. Plan
        open_ms = self._dispense_ms_for_pass(pid)

        # if self._credits < CREDIT_DISPENSE_COST:
        #     print(f"[DISPENSE] blocked: low credits={self._credits:.3f}")
        #     return

        if self._dispense_since_last_charge >= MAX_DISPENSES_PER_CHARGE:
            if not self._pulse_active:
                print("[PRESSURE] periodic reset — forcing recharge")
                self._force_repressurise(now)
            return


        if self._credits < MIN_SAFE_CREDITS:
            if not self._pulse_active:
                print("[DISPENSE] forcing repressurise before dispense")
                self._force_repressurise(now)
            return
        

        print(f"[DISPENSE] PASS {pid} → firing {open_ms}ms")


        cmd_id = self.executor.send_command({
            "name": "dispense.open",
            "payload": {"open_ms": open_ms}
        })

        if cmd_id:
            self._rate_accumulator -= 1.0
            machine.dispense_fired_for_gap = True    
            machine.dispense_skipped_for_gap = False
            machine.last_dispense_cmd_id = cmd_id
            machine.last_dispense_open_ms = open_ms
            self._dispense_since_last_charge += 1   # ✅ increment ONLY after actual fire



        # print(
        #     f"[DISPENSE DECISION] "
        #     f"pid={pid} allowed={allowed} skip_n={self._skip_n}"
        # )

        # if not allowed:
        #     return

        # machine.dispense_fired_for_gap = True

        # 3. Execute
        # self.executor.send_command({
        #     "name": "dispense.open",
        #     "payload": {"open_ms": open_ms}
        # })

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

        from app.state.machine_state import machine_state_manager
        machine = machine_state_manager.state

        if machine.dispense_fired_for_gap and machine.last_dispense_open_ms is not None:
            self.on_dispense_complete(machine.last_dispense_open_ms)

        # 🔴 RESET FOR NEXT GAP
        machine.last_dispense_open_ms = None
        machine.dispense_fired_for_gap = False
        machine.dispense_skipped_for_gap = False   # 🔴 ADD THIS
        machine.last_dispense_cmd_id = None
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
