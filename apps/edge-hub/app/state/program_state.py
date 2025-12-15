from dataclasses import dataclass, field
import time


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
    running: bool = False
    current_pass: int = 0
    passes: dict = field(default_factory=dict)

    total_expected_paint: float = 0
    total_actual_paint: float = 0

    program_start_ts: float = 0
    last_event: str = None
    last_event_ts: float = 0

    def is_running(self):
        return self.running

    def start_program(self):
        print("[PROGRAM_STATE] START PROGRAM CALLED", id(self))
        self.running = True
        self.program_start_ts = time.time()
        self.current_pass = 0
        self.passes = {}
        self.total_actual_paint = 0
        self.total_expected_paint = 0

    def stop_program(self):
        print("[PROGRAM_STATE] STOP PROGRAM CALLED")
        self.running = False

    def new_pass(self):
        self.current_pass += 1
        pid = self.current_pass

        self.passes[pid] = PassInfo(
            pass_id=pid,
            enter_ts=time.time(),
        )
        self.last_event = "pass_enter"
        self.last_event_ts = time.time()
        return pid

    def mark_stable(self, pid):
        if pid not in self.passes:
            return
        self.passes[pid].stable_ts = time.time()
        self.last_event = "pass_stable"
        self.last_event_ts = time.time()

    def mark_exit(self, pid):
        if pid not in self.passes:
            return
        p = self.passes[pid]
        p.exit_ts = time.time()
        p.status = "completed"

        self.total_expected_paint += p.expected_paint
        self.total_actual_paint += p.actual_paint

        self.last_event = "pass_exit"
        self.last_event_ts = time.time()

    def serialize(self):
        return {
            "running": self.running,
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


program_state = ProgramState()
