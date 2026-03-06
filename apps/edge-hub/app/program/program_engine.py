# app/program/program_engine.py

import time

from app.state.program_state import program_state, ProgramPhase
from app.state.material_state import material_state_manager
from app.services.command_executor import CommandExecutor
from app.services.rule_engine import get_rule_engine
from app.config.paint_profile import PaintProfile, get_profile, DEFAULT_PROFILE
from app.orchestrators.mid_refill_orchestrator import MidRefillOrchestrator

from app.program.strategies.base_strategy import DispenseContext
from app.program.strategies.time_based import TimeBasedStrategy
from app.program.strategies.gravimetric import GravimetricStrategy

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
        # Mid-refill orchestrator
        self.mid_refill_orchestrator = MidRefillOrchestrator(executor)
        self.strategy = None
        # self._refill_state = "IDLE"       # IDLE | FILLING | SETTLING
        # self._refill_weight_before = 0.0
        # self._refill_fill_stop_sent = False
        # self._refill_settle_start = 0.0
        # self._last_refill_ts = 0.0
        # self._refill_attempts = 0
        # self.consecutive_failed_refills = 0

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
        self.mid_refill_orchestrator.reset()

        # self._startup_sent = False
        # self._refill_state = "IDLE"
        # self._refill_weight_before = 0.0
        # self._refill_fill_stop_sent = False
        # self._refill_settle_start = 0.0
        # self._last_refill_ts = 0.0
        # self._refill_attempts = 0
        # self.consecutive_failed_refills = 0

        # Reset startup orchestrator
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
        self.set_phase(ProgramPhase.ABORT, reason or "abort")
        mode_manager.set_operation(OperationMode.manual)
        mode_manager.set_process(ProcessMode.idle)

    def stop_program(self):
        print("[PROGRAM_ENGINE] STOP PROGRAM")
        from app.modes.mode_manager import mode_manager
        from app.modes.mode_types import OperationMode, ProcessMode

        self.executor.send_command({"name": "program.stop", "payload": {}})
        program_state.stop_program()

        # Always reset modes — program.load requires manual + idle
        mode_manager.set_operation(OperationMode.manual)
        mode_manager.set_process(ProcessMode.idle)
        print("[PROGRAM_ENGINE] Modes reset → manual/idle")



    # ──────────────────────────────────────────────────────────────
    # Main event loop — called every telemetry tick
    # ──────────────────────────────────────────────────────────────
    def on_event(self, machine, program):
        ps = program
        print(f"[PROGRAM_ENGINE] phase={ps.phase}")

        if self.executor.is_busy():
            return

        if ps.phase == ProgramPhase.STARTED:
            return   # waiting for program.load ACK

        # if ps.phase == ProgramPhase.LOADED:
        #     ps.begin_startup()
        #     return

        # if ps.phase == ProgramPhase.STARTUP:
        #     self._handle_startup()
        #     return

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
            self.mid_refill_orchestrator.process()
            return

        if ps.phase not in (ProgramPhase.READY, ProgramPhase.RUNNING):
            return

        # Mid-run refill check (only in RUNNING)
        if ps.phase == ProgramPhase.RUNNING:
            mat = material_state_manager.state
            if (
                mat.current_pot_kg < self.profile.mid_refill_threshold_kg
                and not self.executor.is_busy()
            ):
                self.mid_refill_orchestrator.begin(self.profile)

        # if ps.phase == ProgramPhase.RUNNING:
        #     self._maybe_trigger_refill()

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
    # def _handle_startup(self):
    #     if self._startup_sent:
    #         return
    #     print("[PROGRAM_ENGINE] Sending startup.sequence to firmware")
    #     self._startup_sent = True
    #     self.executor.send_command({"name": "startup.sequence", "payload": {}})
    #     # startup_orchestrator.begin() is called from command_executor
    #     # when startup.sequence command.completed ACK arrives

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
    # def _maybe_trigger_refill(self):
    #     mat = material_state_manager.state
    #     p = self.profile
    #     now = time.time()

    #     if mat.current_pot_kg >= p.mid_refill_threshold_kg:
    #         return
    #     if now - self._last_refill_ts < p.mid_refill_cooldown_s:
    #         return
    #     if self._refill_state != "IDLE":
    #         return
    #     if self.executor.is_busy():
    #         return
    #     if self.consecutive_failed_refills >= p.mid_refill_max_failures:
    #         print(
    #             f"[PROGRAM_ENGINE] Refill lockout — "
    #             f"{self.consecutive_failed_refills} consecutive failures "
    #             f"(reservoir likely empty)"
    #         )
    #         return

    #     print(
    #         f"[PROGRAM_ENGINE] Mid-run refill triggered — "
    #         f"pot={mat.current_pot_kg:.3f}kg < threshold={p.mid_refill_threshold_kg}kg"
    #     )

    #     self._refill_weight_before = mat.current_pot_kg
    #     self._refill_fill_stop_sent = False
    #     self._refill_state = "FILLING"
    #     self._last_refill_ts = now
    #     self._refill_attempts += 1

    #     program_state.begin_mid_refill()

    #     self.executor.send_command({
    #         "name": "pot.fill_start",
    #         "payload": {"target_kg": p.mid_refill_target_kg}
    #     })

    # def _handle_mid_refill(self):
    #     mat = material_state_manager.state
    #     p = self.profile
    #     now = time.time()

    #     if self._refill_state == "FILLING":
    #         if not self._refill_fill_stop_sent:
    #             if mat.current_pot_kg >= p.mid_refill_target_kg:
    #                 print(
    #                     f"[PROGRAM_ENGINE] Mid-refill target reached "
    #                     f"({mat.current_pot_kg:.3f}kg) — closing inlet"
    #                 )
    #                 self.executor.send_command({
    #                     "name": "pot.fill_stop",
    #                     "payload": {}
    #                 })
    #                 self._refill_fill_stop_sent = True
    #                 self._refill_settle_start = now
    #                 self._refill_state = "SETTLING"

    #     if self._refill_state == "SETTLING":
    #         if now - self._refill_settle_start >= p.mid_refill_settle_s:
    #             gain = mat.current_pot_kg - self._refill_weight_before
    #             print(
    #                 f"[PROGRAM_ENGINE] Mid-refill settle done — "
    #                 f"gain={gain:.3f}kg (min_expected={p.mid_refill_min_gain_kg}kg)"
    #             )

    #             if gain < p.mid_refill_min_gain_kg:
    #                 self.consecutive_failed_refills += 1
    #                 print(
    #                     f"[PROGRAM_ENGINE] Refill underperformed — "
    #                     f"suspect reservoir low "
    #                     f"({self.consecutive_failed_refills}/{p.mid_refill_max_failures})"
    #                 )
    #             else:
    #                 self.consecutive_failed_refills = 0
    #                 print("[PROGRAM_ENGINE] Refill successful")

    #             self._refill_state = "IDLE"
    #             program_state.on_mid_refill_done()  # → RUNNING

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


# program_engine = None

from app.services.command_executor import command_executor

program_engine = ProgramEngine(command_executor)