import time
from .mode_types import OperationMode, ProcessMode, PressureMode, VisionMode, FaultMode

class ModeManager:
    def __init__(self):
        self.mode_state = {
            "operation": OperationMode.manual,
            "process": ProcessMode.idle,
            "pressure": PressureMode.normal,
            "vision": VisionMode.vision_ok,
            "fault": FaultMode.none,
            "updated_at": time.time()
        }

    def get(self):
        return self.mode_state

    def set_operation(self, mode: OperationMode):
        self.mode_state["operation"] = mode
        self.mode_state["updated_at"] = time.time()
        return self.get()

    def set_process(self, mode: ProcessMode):
        self.mode_state["process"] = mode
        self.mode_state["updated_at"] = time.time()
        return self.get()

    def set_pressure(self, mode: PressureMode):
        self.mode_state["pressure"] = mode
        self.mode_state["updated_at"] = time.time()
        return self.get()

    def set_vision(self, mode: VisionMode):
        self.mode_state["vision"] = mode
        self.mode_state["updated_at"] = time.time()
        return self.get()

    def set_fault(self, mode: FaultMode):
        self.mode_state["fault"] = mode
        self.mode_state["updated_at"] = time.time()
        return self.get()

mode_manager = ModeManager()
