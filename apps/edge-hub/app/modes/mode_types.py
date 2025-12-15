from enum import Enum

class OperationMode(str, Enum):
    manual = "manual"
    semi_auto = "semi_auto"
    auto = "auto"
    idle = "idle"

class ProcessMode(str, Enum):
    idle = "idle"
    tracking = "tracking"
    window_detected = "window_detected"
    dispensing = "dispensing"
    refill = "refill"

class PressureMode(str, Enum):
    normal = "normal"
    low_pressure = "low_pressure"
    over_pressure = "over_pressure"

class VisionMode(str, Enum):
    vision_ok = "vision_ok"
    camera_lost = "camera_lost"
    occluded = "occluded"

class FaultMode(str, Enum):
    none = "none"
    minor = "minor"
    major = "major"
