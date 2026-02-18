from dataclasses import dataclass, field
import time
from enum import Enum
from app.core import clock

class ProgramPhase(str, Enum):
    NONE = "none"
    STARTED = "started"
    LOADED = "loaded"
    STARTUP = "startup"
    READY = "ready"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    CLEANING = "cleaning"
    PURGE = "purge"
    ABORT = "abort"


@dataclass
class PassInfo:
    pass_id: int

    enter_ts: float = 0
    stable_ts: float = 0
    exit_ts: float = 0

    expected_paint: float = 0
    actual_paint: float = 0
    thickness_estimate: float = 0

    status: str = "running"


@dataclass
class ProgramState:
    # running: bool = False
    phase: ProgramPhase = ProgramPhase.NONE

    current_pass: int = 0
    passes: dict = field(default_factory=dict)

    total_expected_paint: float = 0
    total_actual_paint: float = 0

    program_start_ts: float = 0
    last_event: str = None
    last_event_ts: float = 0

    # def is_running(self):
    #     return self.running

    def is_active(self):
        return self.phase in (
            ProgramPhase.STARTUP,
            ProgramPhase.READY,
            ProgramPhase.RUNNING
        )

    def set_phase(self, phase: ProgramPhase, reason: str = None):
        print(f"[PROGRAM_STATE] phase → {phase} ({reason})")
        self.phase = phase
        self.last_event = reason
        self.last_event_ts = clock.mono()

    def on_loaded(self):
        if self.phase == ProgramPhase.STARTED:
            self.set_phase(ProgramPhase.LOADED, "firmware_loaded")

    def begin_startup(self):
        if self.phase == ProgramPhase.LOADED:
            self.set_phase(ProgramPhase.STARTUP, "startup_begin")

    def on_startup_complete(self):
        if self.phase == ProgramPhase.STARTUP:
            self.set_phase(ProgramPhase.READY, "startup_complete")



    # def start_program(self):
    #     print("[PROGRAM_STATE] START PROGRAM CALLED", id(self))
    #     self.running = True
    #     self.program_start_ts = time.time()
    #     self.current_pass = 0
    #     self.passes = {}
    #     self.total_actual_paint = 0
    #     self.total_expected_paint = 0

    def start_program(self):
        self.set_phase(ProgramPhase.STARTED, "operator_start")
        self.program_start_ts = clock.mono()
        self.current_pass = 0
        self.passes = {}
        self.total_actual_paint = 0
        self.total_expected_paint = 0

    def stop_program(self):
        self.set_phase(ProgramPhase.STOPPED, "operator_stop")

    def abort(self, reason: str = None):
        self.set_phase(ProgramPhase.ABORT, reason or "abort")


    # def stop_program(self):
    #     print("[PROGRAM_STATE] STOP PROGRAM CALLED")
    #     self.running = False

    def new_pass(self):

        if self.phase == ProgramPhase.READY:
            self.set_phase(ProgramPhase.RUNNING, "first_pass_enter")

        self.current_pass += 1
        pid = self.current_pass

        self.passes[pid] = PassInfo(
            pass_id=pid,
            enter_ts=clock.mono(),
        )
        self.last_event = "pass_enter"
        self.last_event_ts = clock.mono()
        return pid

    def mark_stable(self, pid):
        if pid not in self.passes:
            return
        self.passes[pid].stable_ts = clock.mono()
        self.last_event = "pass_stable"
        self.last_event_ts = clock.mono()

    def mark_exit(self, pid):
        if pid not in self.passes:
            return
        p = self.passes[pid]
        p.exit_ts = clock.mono()
        p.status = "completed"

        self.total_expected_paint += p.expected_paint
        self.total_actual_paint += p.actual_paint

        self.last_event = "pass_exit"
        self.last_event_ts = clock.mono()

    def serialize(self):
        return {
            "phase": self.phase.value,
            "current_pass": self.current_pass,
            "passes": {
                pid: {
                    "enter_ts": p.enter_ts,
                    "stable_ts": p.stable_ts,
                    "exit_ts": p.exit_ts,
                    "expected_paint": p.expected_paint,
                    "actual_paint": p.actual_paint,
                    "thickness_estimate": p.thickness_estimate,
                    "status": p.status,
                }
                for pid, p in self.passes.items()
            },
            "total_expected_paint": self.total_expected_paint,
            "total_actual_paint": self.total_actual_paint,
            "last_event": self.last_event,
            "last_event_ts": self.last_event_ts,
            "program_start_ts": self.program_start_ts
        }


    # def serialize(self):
    #     return {
    #         "running": self.running,
    #         "current_pass": self.current_pass,
    #         "passes": {
    #             pid: {
    #                 "enter_ts": p.enter_ts,
    #                 "stable_ts": p.stable_ts,
    #                 "exit_ts": p.exit_ts,
    #                 "expected_paint": p.expected_paint,
    #                 "actual_paint": p.actual_paint,
    #                 "thickness_estimate": p.thickness_estimate,
    #                 "status": p.status,
    #             }
    #             for pid, p in self.passes.items()
    #         },
    #         "total_expected_paint": self.total_expected_paint,
    #         "total_actual_paint": self.total_actual_paint,
    #         "last_event": self.last_event,
    #         "last_event_ts": self.last_event_ts,
    #         "program_start_ts": self.program_start_ts
    #     }


program_state = ProgramState()
