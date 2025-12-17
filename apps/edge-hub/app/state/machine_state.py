from dataclasses import dataclass, field
import time
from enum import Enum

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


    phase: MachinePhase = MachinePhase.INIT



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
            self.plate_stable = False
            self.plate_stable_since = time.time()
            self.last_event = "plate_enter"
            self.last_event_ts = time.time()
            return

        # ----------- EXIT (single-shot) -----------
        if old == 1 and g == 0:
            self.gap_transition = "exit"
            self.plate_stable = False
            self.last_event = "plate_exit"
            self.last_event_ts = time.time()
            return

        # otherwise no transition
        self.gap_transition = None

    def derive_phase(self):
            # TEMP LOGIC (OFFICE SAFE)
            if self.gap == 0:
                self.phase = MachinePhase.MOVING
            elif self.gap == 1 and self.plate_stable:
                self.phase = MachinePhase.REST_DISPENSE_EDGE

    # ------------------------------
    # FIXED stable window detection
    # ------------------------------
    def check_stable_window(self):
        if self.gap == 1:
            if not self.plate_stable:
                elapsed_ms = (time.time() - self.plate_stable_since) * 1000
                if elapsed_ms >= self.stable_window_ms:
                    self.plate_stable = True
                    self.last_event = "plate_stable"
                    self.last_event_ts = time.time()
        return self.plate_stable


class MachineStateManager:
    def __init__(self):
        self.state = MachineState()

    def apply_telemetry(self, data):
        if "pressure" in data:
            self.state.pressure = data["pressure"]

        if "flow" in data:
            self.state.flow = data["flow"]

        if "gap" in data:
            self.state.update_gap(int(data["gap"]))

        self.state.last_update_ts = data.get("ts", time.time())
        self.state.check_stable_window()

        self.state.derive_phase()

        return self.state
    
    

machine_state_manager = MachineStateManager()
