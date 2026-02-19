# app/program/program_engine.py

import time

from app.state.program_state import program_state, ProgramPhase
from app.state.material_state import material_state_manager
from app.services.command_executor import CommandExecutor
from app.services.rule_engine import get_rule_engine
from app.config.paint_profile import PaintProfile, get_profile, DEFAULT_PROFILE


class ProgramEngine:
    """
    Drives program lifecycle:
      start_program() → STARTED → LOADED → STARTUP
          → startup_orchestrator.begin() takes over →
      POT_FILLING → PRESSURISING → LINE_PRIMING → READY → RUNNING
          ↕ MID_REFILLING (transparent, returns to RUNNING)
    """

    def __init__(self, executor: CommandExecutor):
        self.executor = executor
        self.rule_engine = get_rule_engine(executor=executor)
        self.config: dict = {}
        self.profile: PaintProfile = DEFAULT_PROFILE

        # Startup
        self._startup_sent = False

        # Mid-run refill state machine
        self._refill_state = "IDLE"       # IDLE | FILLING | SETTLING
        self._refill_weight_before = 0.0
        self._refill_fill_stop_sent = False
        self._refill_settle_start = 0.0
        self._last_refill_ts = 0.0
        self._refill_attempts = 0
        self.consecutive_failed_refills = 0

    # ──────────────────────────────────────────────────────────────
    # API
    # ──────────────────────────────────────────────────────────────
    def start_program(self, config: dict):
        print(f"[PROGRAM_ENGINE] START PROGRAM config={config}")
        self.config = config

        # Load paint profile for this program run
        profile_name = config.get("paint_profile")
        self.profile = get_profile(profile_name)

        # Reset all state
        self._startup_sent = False
        self._refill_state = "IDLE"
        self._refill_weight_before = 0.0
        self._refill_fill_stop_sent = False
        self._refill_settle_start = 0.0
        self._last_refill_ts = 0.0
        self._refill_attempts = 0
        self.consecutive_failed_refills = 0

        # Reset startup orchestrator
        from app.orchestrators.startup_orchestrator import startup_orchestrator
        startup_orchestrator.reset()

        program_state.start_program()

        self.executor.send_command({
            "name": "program.load",
            "payload": {"program_id": config.get("program_id", "default")}
        })

    def stop_program(self):
        print("[PROGRAM_ENGINE] STOP PROGRAM")
        self.executor.send_command({"name": "program.stop", "payload": {}})
        program_state.stop_program()

    # ──────────────────────────────────────────────────────────────
    # Main event loop — called every telemetry tick
    # ──────────────────────────────────────────────────────────────
    def on_event(self, machine, program):
        ps = program
        print(f"[PROGRAM_ENGINE] phase={ps.phase}")


        if ps.phase == ProgramPhase.STARTED:
            return   # waiting for program.load ACK

        if ps.phase == ProgramPhase.LOADED:
            ps.begin_startup()
            return

        if ps.phase == ProgramPhase.STARTUP:
            self._handle_startup()
            return

        # Startup orchestrator owns these phases
        if ps.phase in (
            ProgramPhase.POT_FILLING,
            ProgramPhase.PRESSURISING,
            ProgramPhase.LINE_PRIMING,
        ):
            from app.orchestrators.startup_orchestrator import startup_orchestrator
            startup_orchestrator.process()
            return

        if ps.phase == ProgramPhase.MID_REFILLING:
            self._handle_mid_refill()
            return

        if ps.phase not in (ProgramPhase.READY, ProgramPhase.RUNNING):
            return

        # Mid-run refill check (only in RUNNING)
        if ps.phase == ProgramPhase.RUNNING:
            self._maybe_trigger_refill()

        # Gap/dispense events
        event = ps.last_event

        if event == "pass_enter":
            self._handle_pass_enter(ps)
        elif event == "pass_stable":
            self._handle_pass_stable(ps, machine)
        elif event == "pass_exit":
            self._handle_pass_exit(ps)

        ps.last_event = None

    # ──────────────────────────────────────────────────────────────
    # STARTUP: send startup.sequence firmware command once
    # ──────────────────────────────────────────────────────────────
    def _handle_startup(self):
        if self._startup_sent:
            return
        print("[PROGRAM_ENGINE] Sending startup.sequence to firmware")
        self._startup_sent = True
        self.executor.send_command({"name": "startup.sequence", "payload": {}})
        # startup_orchestrator.begin() is called from command_executor
        # when startup.sequence command.completed ACK arrives

    # ──────────────────────────────────────────────────────────────
    # PASS EVENTS
    # ──────────────────────────────────────────────────────────────
    def _handle_pass_enter(self, program):
        pid = program.current_pass
        print(f"[PROGRAM_ENGINE] PASS {pid} ENTER")

    def _handle_pass_stable(self, program, machine):
        pid = program.current_pass
        print(f"[PROGRAM_ENGINE] PASS {pid} STABLE → DISPENSE OPEN")

        if not machine.is_dispense_window():
            print(f"[PROGRAM_ENGINE] PASS {pid} not in dispense window — skip")
            return

        open_ms = self._dispense_ms_for_pass(pid)
        p = program.passes.get(pid)
        if p:
            # Record expected using effective time (accounts for lags)
            effective_ms = max(0, open_ms - self.profile.nozzle_open_lag_ms - self.profile.nozzle_close_lag_ms)
            p.expected_paint = effective_ms   # store ms as proxy until flow sensor added
            print(
                f"[PROGRAM_ENGINE] PASS {pid} dispense — "
                f"solenoid_open_ms={open_ms} "
                f"effective_ms={effective_ms} "
                f"(open_lag={self.profile.nozzle_open_lag_ms}ms "
                f"close_lag={self.profile.nozzle_close_lag_ms}ms)"
            )

        self.executor.send_command({
            "name": "dispense.open",
            "payload": {"open_ms": open_ms}
        })

    def _handle_pass_exit(self, program):
        pid = program.current_pass
        print(f"[PROGRAM_ENGINE] PASS {pid} EXIT → DISPENSE STOP")
        self.executor.send_command({
            "name": "dispense.stop",
            "payload": {}
        })

    # ──────────────────────────────────────────────────────────────
    # MID-RUN REFILL
    # Triggered from RUNNING when pot drops below profile threshold.
    # State machine: IDLE → FILLING → SETTLING → IDLE
    # ──────────────────────────────────────────────────────────────
    def _maybe_trigger_refill(self):
        mat = material_state_manager.state
        p = self.profile
        now = time.time()

        if mat.current_pot_kg >= p.mid_refill_threshold_kg:
            return
        if now - self._last_refill_ts < p.mid_refill_cooldown_s:
            return
        if self._refill_state != "IDLE":
            return
        if self.executor.is_busy():
            return
        if self.consecutive_failed_refills >= p.mid_refill_max_failures:
            print(
                f"[PROGRAM_ENGINE] Refill lockout — "
                f"{self.consecutive_failed_refills} consecutive failures "
                f"(reservoir likely empty)"
            )
            return

        print(
            f"[PROGRAM_ENGINE] Mid-run refill triggered — "
            f"pot={mat.current_pot_kg:.3f}kg < threshold={p.mid_refill_threshold_kg}kg"
        )

        self._refill_weight_before = mat.current_pot_kg
        self._refill_fill_stop_sent = False
        self._refill_state = "FILLING"
        self._last_refill_ts = now
        self._refill_attempts += 1

        program_state.begin_mid_refill()

        self.executor.send_command({
            "name": "pot.fill_start",
            "payload": {"target_kg": p.mid_refill_target_kg}
        })

    def _handle_mid_refill(self):
        mat = material_state_manager.state
        p = self.profile
        now = time.time()

        if self._refill_state == "FILLING":
            if not self._refill_fill_stop_sent:
                if mat.current_pot_kg >= p.mid_refill_target_kg:
                    print(
                        f"[PROGRAM_ENGINE] Mid-refill target reached "
                        f"({mat.current_pot_kg:.3f}kg) — closing inlet"
                    )
                    self.executor.send_command({
                        "name": "pot.fill_stop",
                        "payload": {}
                    })
                    self._refill_fill_stop_sent = True
                    self._refill_settle_start = now
                    self._refill_state = "SETTLING"

        if self._refill_state == "SETTLING":
            if now - self._refill_settle_start >= p.mid_refill_settle_s:
                gain = mat.current_pot_kg - self._refill_weight_before
                print(
                    f"[PROGRAM_ENGINE] Mid-refill settle done — "
                    f"gain={gain:.3f}kg (min_expected={p.mid_refill_min_gain_kg}kg)"
                )

                if gain < p.mid_refill_min_gain_kg:
                    self.consecutive_failed_refills += 1
                    print(
                        f"[PROGRAM_ENGINE] Refill underperformed — "
                        f"suspect reservoir low "
                        f"({self.consecutive_failed_refills}/{p.mid_refill_max_failures})"
                    )
                else:
                    self.consecutive_failed_refills = 0
                    print("[PROGRAM_ENGINE] Refill successful")

                self._refill_state = "IDLE"
                program_state.on_mid_refill_done()  # → RUNNING

    # ──────────────────────────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────────────────────────
    def _dispense_ms_for_pass(self, pid: int) -> int:
        """
        Return solenoid open_ms for this pass.
        Priority: per-pass config > profile default.
        """
        passes = self.config.get("passes", {})
        pass_cfg = passes.get(str(pid), {})

        # Per-pass override takes priority
        if "open_ms" in pass_cfg:
            return int(pass_cfg["open_ms"])

        # Profile default
        return self.profile.dispense_open_ms


program_engine = None

# # app/program/program_engine.py

# import time
# from app.state.program_state import program_state, ProgramPhase
# from app.state.material_state import material_state_manager
# from app.services.command_executor import CommandExecutor
# from app.services.rule_engine import get_rule_engine

# # ── Tunable constants ──────────────────────────────────────────────
# MID_REFILL_THRESHOLD_KG  = 0.8   # trigger refill below this
# MID_REFILL_TARGET_KG     = 3.5   # fill to this
# MID_REFILL_MIN_GAIN_KG   = 0.2   # if less gained → suspect reservoir low
# MID_REFILL_SETTLE_S      = 3.0   # wait after fill_stop before resuming
# MID_REFILL_COOLDOWN_S    = 15
# MID_REFILL_MAX_ATTEMPTS  = 3


# class ProgramEngine:
#     def __init__(self, executor: CommandExecutor):
#         self.executor = executor
#         self.rule_engine = get_rule_engine(executor=executor)
#         self.config = None
#         self._startup_sent = False

#         # Mid-run refill state machine
#         self._refill_state = "IDLE"   # IDLE | FILLING | SETTLING
#         self._refill_weight_before = 0.0
#         self._refill_fill_stop_sent = False
#         self._refill_settle_start = 0.0
#         self._last_refill_ts = 0.0
#         self._refill_attempts = 0
#         self.consecutive_failed_refills = 0

#     # ──────────────────────────────────────────────────────────────
#     # API: called by FastAPI route /program/start
#     # ──────────────────────────────────────────────────────────────
#     def start_program(self, config: dict):
#         print("[PROGRAM_ENGINE] START PROGRAM")
#         self.config = config
#         self._startup_sent = False

#         from app.orchestrators.startup_orchestrator import startup_orchestrator
#         startup_orchestrator.reset()

#         program_state.start_program()

#         self.executor.send_command({
#             "name": "program.load",
#             "payload": {"program_id": config.get("program_id", "default")}
#         })

#     # ──────────────────────────────────────────────────────────────
#     # API: called by FastAPI route /program/stop
#     # ──────────────────────────────────────────────────────────────
#     def stop_program(self):
#         print("[PROGRAM_ENGINE] STOP PROGRAM")
#         self.executor.send_command({"name": "program.stop", "payload": {}})
#         program_state.stop_program()

#     # ──────────────────────────────────────────────────────────────
#     # Called every telemetry tick by state_orchestrator
#     # ──────────────────────────────────────────────────────────────
#     def on_event(self, machine, program):
#         ps = program

#         # ── Waiting for program.load ACK ──
#         if ps.phase == ProgramPhase.STARTED:
#             return

#         # ── program.load completed → trigger startup.sequence ──
#         if ps.phase == ProgramPhase.LOADED:
#             ps.begin_startup()

#         if ps.phase == ProgramPhase.STARTUP:
#             self._handle_startup()
#             return

#         # ── startup.sequence ACK done → hand off to startup_orchestrator ──
#         if ps.phase == ProgramPhase.POT_FILLING:
#             from app.orchestrators.startup_orchestrator import startup_orchestrator
#             startup_orchestrator.process()
#             return

#         if ps.phase == ProgramPhase.PRESSURISING:
#             from app.orchestrators.startup_orchestrator import startup_orchestrator
#             startup_orchestrator.process()
#             return

#         if ps.phase == ProgramPhase.LINE_PRIMING:
#             from app.orchestrators.startup_orchestrator import startup_orchestrator
#             startup_orchestrator.process()
#             return

#         # ── Mid-run refill ──
#         if ps.phase == ProgramPhase.MID_REFILLING:
#             self._handle_mid_refill()
#             return

#         # ── Normal running ──
#         if ps.phase not in (ProgramPhase.READY, ProgramPhase.RUNNING):
#             return

#         if ps.phase == ProgramPhase.RUNNING:
#             self._maybe_trigger_refill()

#         event = ps.last_event

#         if event == "pass_enter":
#             self._handle_pass_enter(ps)
#         elif event == "pass_stable":
#             self._handle_pass_stable(ps, machine)
#         elif event == "pass_exit":
#             self._handle_pass_exit(ps)

#         ps.last_event = None

#     # ──────────────────────────────────────────────────────────────
#     # STARTUP: send startup.sequence once
#     # ──────────────────────────────────────────────────────────────
#     def _handle_startup(self):
#         if self._startup_sent:
#             return

#         print("[PROGRAM_ENGINE] Sending startup.sequence to firmware")
#         self._startup_sent = True
#         self.executor.send_command({"name": "startup.sequence", "payload": {}})
#         # startup_orchestrator.begin() is called from command_executor
#         # when startup.sequence ACK completes → triggers POT_FILLING

#     # ──────────────────────────────────────────────────────────────
#     # PASS EVENTS
#     # ──────────────────────────────────────────────────────────────
#     def _handle_pass_enter(self, program):
#         print(f"[PROGRAM_ENGINE] PASS {program.current_pass} ENTER")

#     def _handle_pass_stable(self, program, machine):
#         pid = program.current_pass
#         print(f"[PROGRAM_ENGINE] PASS {pid} STABLE → DISPENSE OPEN")

#         if not machine.is_dispense_window():
#             return

#         open_ms = self._dispense_ms_for_pass(pid)
#         p = program.passes.get(pid)
#         if p:
#             p.expected_paint = open_ms / 1000.0  # rough estimate

#         self.executor.send_command({
#             "name": "dispense.open",
#             "payload": {"open_ms": open_ms}
#         })

#     def _handle_pass_exit(self, program):
#         pid = program.current_pass
#         print(f"[PROGRAM_ENGINE] PASS {pid} EXIT → DISPENSE STOP")
#         self.executor.send_command({
#             "name": "dispense.stop",
#             "payload": {}
#         })

#     # ──────────────────────────────────────────────────────────────
#     # MID-RUN REFILL — state machine
#     # IDLE → FILLING → SETTLING → IDLE (or FAILED)
#     # ──────────────────────────────────────────────────────────────
#     def _maybe_trigger_refill(self):
#         mat = material_state_manager.state
#         now = time.time()

#         if mat.current_pot_kg >= MID_REFILL_THRESHOLD_KG:
#             return
#         if now - self._last_refill_ts < MID_REFILL_COOLDOWN_S:
#             return
#         if self._refill_state != "IDLE":
#             return
#         if self.executor.is_busy():
#             return

#         if self.consecutive_failed_refills >= MID_REFILL_MAX_ATTEMPTS:
#             print("[PROGRAM_ENGINE] Refill lockout — reservoir likely empty")
#             return

#         print(f"[PROGRAM_ENGINE] Mid-run refill triggered (pot={mat.current_pot_kg:.2f}kg)")

#         self._refill_weight_before = mat.current_pot_kg
#         self._refill_fill_stop_sent = False
#         self._refill_state = "FILLING"
#         self._last_refill_ts = now
#         self._refill_attempts += 1

#         program_state.begin_mid_refill()

#         self.executor.send_command({
#             "name": "pot.fill_start",
#             "payload": {"target_kg": MID_REFILL_TARGET_KG}
#         })

#     def _handle_mid_refill(self):
#         mat = material_state_manager.state
#         now = time.time()

#         # ── FILLING: watch weight, close when target reached ──
#         if self._refill_state == "FILLING":
#             if not self._refill_fill_stop_sent:
#                 if mat.current_pot_kg >= MID_REFILL_TARGET_KG:
#                     print(f"[PROGRAM_ENGINE] Mid-refill target reached ({mat.current_pot_kg:.2f}kg) → closing inlet")
#                     self.executor.send_command({"name": "pot.fill_stop", "payload": {}})
#                     self._refill_fill_stop_sent = True
#                     self._refill_settle_start = now

#         # ── SETTLING: wait for weight to stabilise ──
#         if self._refill_fill_stop_sent:
#             if now - self._refill_settle_start >= MID_REFILL_SETTLE_S:
#                 gain = mat.current_pot_kg - self._refill_weight_before
#                 print(f"[PROGRAM_ENGINE] Mid-refill settle done — gain={gain:.3f}kg")

#                 if gain < MID_REFILL_MIN_GAIN_KG:
#                     self.consecutive_failed_refills += 1
#                     print(f"[PROGRAM_ENGINE] Refill underperformed ({gain:.3f}kg) — suspect reservoir low ({self.consecutive_failed_refills}/{MID_REFILL_MAX_ATTEMPTS})")
#                 else:
#                     self.consecutive_failed_refills = 0

#                 self._refill_state = "IDLE"
#                 program_state.on_mid_refill_done()   # → RUNNING

#     # ──────────────────────────────────────────────────────────────
#     # Helper
#     # ──────────────────────────────────────────────────────────────
#     def _dispense_ms_for_pass(self, pid):
#         passes = (self.config or {}).get("passes", {})
#         return passes.get(str(pid), {}).get("open_ms", 200)


# program_engine = None


#  OLDES
# # app/program/program_engine.py

# from dataclasses import field
# import time
# import uuid

# from app.state.program_state import program_state
# from app.services.command_executor import CommandExecutor
# from app.services.rule_engine import get_rule_engine
# from app.state.program_state import ProgramPhase


# class ProgramEngine:
#     def __init__(self, executor: CommandExecutor):
#         self.executor = executor
#         self.rule_engine = get_rule_engine(executor=executor)
#         self.config = None  # loaded program config from NestJS
#         self.startup_started_at = None
#         self.pass_started_at = None

#         self.refill_state = "IDLE"   # IDLE | REQUESTED | RUNNING
#         self.last_refill_ts = 0
#         self.refill_threshold_kg = 0.5   # trigger below this
#         self.refill_target_kg = 4.0      # stop expecting above this
#         self.refill_cooldown_sec = 5
#         self.refill_attempts = 0
#         self.max_refill_attempts = 3


#     # ---------------------------------------------------------
#     # Called by NestJS: /program/start
#     # ---------------------------------------------------------
#     def start_program(self, config: dict):
#         print("[PROGRAM_ENGINE] START PROGRAM")
#         self.config = config
#         program_state.start_program()
#         # 2. Send program.load to firmware
#         self.executor.send_command({
#             "name": "program.load",
#             "payload": {
#                 "program_id": config.get("program_id", "default")
#             }
#         })

#     # ---------------------------------------------------------
#     # Called by NestJS: /program/stop
#     # ---------------------------------------------------------
#     def stop_program(self):
#         print("[PROGRAM_ENGINE] STOP PROGRAM")
#         self.executor.send_command({
#             "name": "program.stop",
#             "payload": {}
#         })
#         program_state.stop_program()

#     # ---------------------------------------------------------
#     # Called on every new telemetry event AFTER state_orchestrator
#     # ---------------------------------------------------------
#     # def on_event(self, machine, program):
#     #     # if not program.is_running():
#     #     #     return

#     #     if program.phase not in (
#     #         ProgramPhase.READY,
#     #         ProgramPhase.RUNNING
#     #     ):
#     #         return

#     #     # event can be None / enter / stable / exit
#     #     event = program.last_event

#     #     if event == "pass_enter":
#     #         self._handle_pass_enter(program)
#     #     elif event == "pass_stable":
#     #         self._handle_pass_stable(program, machine)
#     #     elif event == "pass_exit":
#     #         self._handle_pass_exit(program)

# # Inside app/program/program_engine.py

#     def _handle_startup(self, machine):
#         # If we already sent it, don't spam
#         if self.startup_started_at is not None:
#             return

#         print("[PROGRAM_ENGINE] System in STARTUP. Sending startup.sequence to firmware.")
#         self.startup_started_at = time.time()
        
#         # This will now pass the Registry check AND the WorkflowBuilder check
#         self.executor.send_command({
#             "name": "startup.sequence",
#             "payload": {}
#         })

#     def on_event(self, machine, program):

#         # --------------------------------------------------
#         # PHASE TRANSITIONS FROM FIRMWARE EVENTS
#         # --------------------------------------------------

#         if program.phase == ProgramPhase.STARTED:
#             # waiting firmware load ack
#             return
        
#         if program.phase == ProgramPhase.LOADED:
#             program.begin_startup()

#         if program.phase == ProgramPhase.STARTUP:
#             self._handle_startup(machine)
#             return

#         # --------------------------------------------------
#         # NORMAL PASS LOGIC
#         # --------------------------------------------------

#         if program.phase not in (
#             ProgramPhase.READY,
#             ProgramPhase.RUNNING
#         ):
#             return
        
#         # if program.last_event == "refill_started":
#         #     self.refill_state = "RUNNING"

#         if program.last_event == "refill_done":
#             self.refill_state = "IDLE"
#             self.last_refill_ts = time.time()


#         if program.phase == ProgramPhase.RUNNING:
#             self._maybe_trigger_refill(machine)

#         event = program.last_event

#         if event == "pass_enter":
#             self._handle_pass_enter(program)

#         elif event == "pass_stable":
#             self._handle_pass_stable(program, machine)

#         elif event == "pass_exit":
#             self._handle_pass_exit(program)
        
#         program.last_event = None


#     # ---------------------------------------------------------
#     def _handle_pass_enter(self, program):
#         pid = program.current_pass
#         print(f"[PROGRAM_ENGINE] PASS {pid} ENTER")
#         # your logic: nothing needed yet

#     # ---------------------------------------------------------
#     # When plate is stable → BEGIN DISPENSE
#     # ---------------------------------------------------------
#     def _handle_pass_stable(self, program, machine):
#         pid = program.current_pass
#         print(f"[PROGRAM_ENGINE] PASS {pid} STABLE → DISPENSE START")

#         if not machine.is_dispense_window():
#             return


#         dispense_ml = self._expected_ml_for_pass(pid)

#         p = program.passes.get(pid)
#         if p:
#             p.expected_paint = dispense_ml


#         self.executor.send_command({
#             "name": "dispense.start",
#             "payload": {
#                 "amount_ml": dispense_ml,
#                 "pass_id": pid
#             }
#         })

#     # ---------------------------------------------------------
#     # When plate exits → END DISPENSE
#     # ---------------------------------------------------------
#     def _handle_pass_exit(self, program):
#         pid = program.current_pass
#         print(f"[PROGRAM_ENGINE] PASS {pid} EXIT → DISPENSE END")

#         dispense_ml = self._expected_ml_for_pass(pid)
#         p = program.passes.get(pid)
#         if p:
#             p.expected_paint = dispense_ml

#         self.executor.send_command({
#             "name": "dispense.stop",
#             "payload": {
#                 "pass_id": pid
#             }
#         })

#     def _maybe_trigger_refill(self, machine):

#         now = time.time()
#         pot_kg = machine.pot_weight_kg

#         from app.state.system_state import system_state, SystemPhase

#         if program_state.phase in (
#             ProgramPhase.ABORT,
#             ProgramPhase.FAULT,
#         ):
#             self.refill_state = "IDLE"
#             return

#         # Hard phase gate
#         if program_state.phase not in (
#             ProgramPhase.STARTUP,
#             ProgramPhase.READY,
#             ProgramPhase.RUNNING,
#         ):
#             return

#         if system_state.phase not in (SystemPhase.READY, SystemPhase.STARTUP):
#             return

#         # -----------------------------------------
#         # 1. Unlock refill if pot recovered
#         # -----------------------------------------
#         # if self.refill_state == "RUNNING":
#         #     if pot_kg >= self.refill_target_kg:
#         #         print("[PROGRAM_ENGINE] Refill completed (target reached)")
#         #         self.refill_state = "IDLE"
#         #         self.refill_attempts = 0
#         #     return

#         # -----------------------------------------
#         # 2. Only trigger below threshold
#         # -----------------------------------------
#         # -----------------------------------------
#         # Trigger only below threshold
#         # -----------------------------------------
#         if pot_kg >= self.refill_threshold_kg:
#             return


#         # -----------------------------------------
#         # 3. Cooldown protection
#         # -----------------------------------------
#         if now - self.last_refill_ts < self.refill_cooldown_sec:
#             return

#         # -----------------------------------------
#         # 4. If already requested → wait
#         # -----------------------------------------
#         if self.refill_state != "IDLE":
#             return

#         # -----------------------------------------
#         # 5. If firmware busy → do nothing
#         # -----------------------------------------
#         if self.executor.is_busy():
#             return
        

#         print(f"[PROGRAM_ENGINE] Triggering refill (pot={pot_kg:.2f}kg)")

#         if self.refill_attempts >= self.max_refill_attempts:
#             print("[PROGRAM_ENGINE] Refill lockout – max attempts reached")
#             return

#         self.executor.send_command({
#             "name": "refill.start",
#             "payload": {}
#         })

#         self.refill_attempts += 1
#         self.refill_state = "REQUESTED"
#         self.last_refill_ts = now

#         # self.executor.send_command({
#         #     "name": "refill.start",
#         #     "payload": {}
#         # })

#         # self.refill_state = "REQUESTED"
#         # self.last_refill_ts = now

#   # ---------------------------------------------------------
#     # helper
#     # ---------------------------------------------------------
#     def _expected_ml_for_pass(self, pid):
#         passes = self.config.get("passes", {})
#         if str(pid) in passes:
#             return passes[str(pid)].get("dispense_ml", 5)
#         return 5


# # global instance injected in app.main
# program_engine = None
