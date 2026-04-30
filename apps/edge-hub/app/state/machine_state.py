from dataclasses import dataclass, field
# import time
from app.core import clock

from enum import Enum
from app.commands.helpers import create_and_queue_command
from app.program.program_engine import program_engine  # or pass via ctor
from app.modes.mode_manager import mode_manager
from app.modes.mode_types import OperationMode, ProcessMode

class MachinePhase(str, Enum):
    INIT = "init"
    MOVING = "moving"
    REST_DISPENSE_EDGE = "rest_dispense_edge"
    REST_FAR_EDGE = "rest_far_edge"
    FAULT = "fault"



@dataclass
class MachineState:
    pressure: float = 0.0
    flow: float = 0.0
    gap: int = 0

    gap_prev: int = 0
    gap_transition: str = None
    plate_stable: bool = False
    plate_stable_since: float = 0.0
    stable_window_ms: int = 200

    valves: dict = field(default_factory=dict)
    is_dispensing: bool = False

    last_event: str = None
    last_event_ts: float = 0.0
    last_update_ts: float = 0.0
    dispense_fired_for_gap: bool = False


    phase: MachinePhase = MachinePhase.INIT

    def is_dispense_window(self):
        return (
            self.phase == MachinePhase.REST_DISPENSE_EDGE
            and self.plate_stable
            and not self.dispense_fired_for_gap
        )

    # ------------------------------
    # FIXED ENTER / EXIT detection
    # ------------------------------
    def update_gap(self, g: int):
        old = self.gap
        self.gap_prev = old
        self.gap = g

        # ----------- ENTER (single-shot) ----------
        if old == 0 and g == 1:
            self.gap_transition = "enter"
            self.dispense_fired_for_gap = False
            self.plate_stable = False
            self.plate_stable_since = clock.mono()
            self.last_event = "plate_enter"
            self.last_event_ts = clock.mono()
            return

        # ----------- EXIT (single-shot) -----------
        if old == 1 and g == 0:
            self.gap_transition = "exit"
            self.plate_stable = False
            # self.dispense_fired_for_gap = False
            self.last_event = "plate_exit"
            self.last_event_ts = clock.mono()
            return

        # otherwise no transition
        self.gap_transition = None

    def derive_phase(self):
        if self.gap == 0:
            self.phase = MachinePhase.MOVING
        elif self.gap == 1:
            if self.plate_stable:
                self.phase = MachinePhase.REST_DISPENSE_EDGE
            else:
                self.phase = MachinePhase.MOVING

    # ------------------------------
    # FIXED stable window detection
    # ------------------------------
    def check_stable_window(self):
        if self.gap == 1:
            if not self.plate_stable:
                elapsed_ms = (clock.mono() - self.plate_stable_since) * 1000
                if elapsed_ms >= self.stable_window_ms:
                    self.plate_stable = True
                    self.last_event = "plate_stable"
                    self.last_event_ts = clock.mono()
        return self.plate_stable


class MachineStateManager:
    def __init__(self):
        self.state = MachineState()
        self._last_seen_pass_id = None

    def apply_telemetry(self, data):
        # -------- PRESSURE --------
        if "pot_pressure" in data:
            self.state.pressure = data["pot_pressure"]

        # -------- GAP SENSOR --------
        if "gap" in data:
            self.state.update_gap(int(data["gap"]))

        # -------- VALVES --------
        if "valves" in data:
            self.state.valves = data["valves"]
            self.state.is_dispensing = bool(data["valves"].get("dispense", 0))

        # -------- TIME --------
        self.state.last_update_ts = clock.mono()

        self.state.check_stable_window()
        self.state.derive_phase()

        from app.state.program_state import program_state
        program_engine.on_event(self.state, program_state)

        pid = program_state.current_pass

        # ✅ RESET latch on pass change
        if pid != self._last_seen_pass_id and self.state.gap_transition == "enter":
            self.state.dispense_fired_for_gap = False
            self._last_seen_pass_id = pid
            print(f"[LATCH RESET] new pass → pid={pid}")

        print(
            f"[PRE-CHECK] "
            f"phase={program_state.phase} "
            f"stable={self.state.plate_stable} "
            f"gap={self.state.gap} "
            f"fired={self.state.dispense_fired_for_gap}"
        )

        # ── REAL-TIME DISPENSE TRIGGER ─────────────────────────
        if (
            self.state.is_dispense_window()
        ):
            # get current pass id (must be maintained by ProgramEngine)
            # pid = program_engine.program_state.current_pass
            from app.state.program_state import program_state
            pid = program_state.current_pass

        # 🔍 DEBUG BLOCK (ADD HERE)
            print(
                f"[REALTIME DEBUG] "
                f"pid={pid} "
                f"phase={program_state.phase} "
                f"stable={self.state.plate_stable} "
                f"gap={self.state.gap} "
                f"fired={self.state.dispense_fired_for_gap}"
            )
            print(f"[PROFILE] skip_n={program_engine._skip_n}")
            allowed = program_engine.should_dispense(pid, self.state)

            print(f"[REALTIME DECISION] allowed={allowed}")

            if allowed:
                print("[REALTIME] FIRING DISPENSE")

                mode_manager.set_operation(OperationMode.auto)
                mode_manager.set_process(ProcessMode.window_detected)

                # open_ms = program_engine._dispense_ms_for_pass(pid)
                open_ms = program_engine.get_dispense_plan(pid)

                create_and_queue_command(
                    name="dispense.open",
                    payload={"open_ms": open_ms}
                )

                self.state.dispense_fired_for_gap = True

        return self.state


        # -------- DERIVED --------
        # self.state.check_stable_window()
        # self.state.derive_phase()

        # return self.state


    # def apply_telemetry(self, data):
    #     if "pressure" in data:
    #         self.state.pressure = data["pressure"]

    #     if "flow" in data:
    #         self.state.flow = data["flow"]

    #     if "gap" in data:
    #         self.state.update_gap(int(data["gap"]))

    #     self.state.last_update_ts = data.get("ts", time.time())
    #     self.state.check_stable_window()

    #     self.state.derive_phase()

    #     return self.state
    
    

machine_state_manager = MachineStateManager()
