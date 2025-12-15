# app/commands/command_registry.py

from typing import Dict, List, Callable, Optional
from app.modes.mode_types import OperationMode, ProcessMode


class CommandSpec:
    def __init__(
        self,
        name: str,
        group: str,
        allowed_operation_modes: Optional[List[OperationMode]] = None,
        allowed_process_modes: Optional[List[ProcessMode]] = None,
        payload_schema: Optional[Dict[str, str]] = None,
        timeout_ms: int = 800,
        priority: int = 10,
        preconditions: Optional[List[Callable]] = None,
        description: str = ""
    ):
        self.name = name
        self.group = group
        self.allowed_operation_modes = allowed_operation_modes or []
        self.allowed_process_modes = allowed_process_modes or []
        self.payload_schema = payload_schema or {}
        self.timeout_ms = timeout_ms
        self.priority = priority
        self.preconditions = preconditions or []
        self.description = description

    # -------------------------------------------------------------------
    def is_allowed_in_mode(self, mode_state):
        """Support both dict-style and object-style mode_state input."""
        operation = (
            getattr(mode_state, "operation", None)
            or mode_state["operation"]
        )
        process = (
            getattr(mode_state, "process", None)
            or mode_state["process"]
        )

        # Check operation mode
        if self.allowed_operation_modes:
            if operation not in self.allowed_operation_modes:
                return False

        # Check process mode
        if self.allowed_process_modes:
            if process not in self.allowed_process_modes:
                return False

        return True

    # -------------------------------------------------------------------
    def check_preconditions(self, device_state):
        for fn in self.preconditions:
            ok, reason = fn(device_state)
            if not ok:
                return False, reason
        return True, None


# =====================================================================
# COMMAND REGISTRY
# =====================================================================

class CommandRegistry:

    def __init__(self):
        self.commands: Dict[str, CommandSpec] = {}
        self._load_defaults()

    def register(self, spec: CommandSpec):
        if spec.name in self.commands:
            raise ValueError("Duplicate command registered")
        self.commands[spec.name] = spec

    def get(self, name: str) -> CommandSpec:
        if name not in self.commands:
            raise KeyError(f"Unknown command: {name}")
        return self.commands[name]

    def list_all(self):
        return list(self.commands.values())

    # =================================================================
    # ALL MACHINE COMMANDS (FINAL)
    # =================================================================
    def _load_defaults(self):
        from app.modes.mode_types import OperationMode, ProcessMode

        # -------------------------------------------------------------
        # DISPENSE GROUP
        # -------------------------------------------------------------
        self.register(CommandSpec(
            name="dispense.open",
            group="dispense",
            allowed_operation_modes=[OperationMode.auto, OperationMode.semi_auto],
            allowed_process_modes=[ProcessMode.dispensing, ProcessMode.window_detected],
            payload_schema={"open_ms": "int"},
            timeout_ms=800,
            priority=20,
            description="Open solenoid for X milliseconds"
        ))

        self.register(CommandSpec(
            name="dispense.stop",
            group="dispense",
            allowed_operation_modes=[OperationMode.auto, OperationMode.semi_auto],
            allowed_process_modes=[ProcessMode.dispensing],
            payload_schema={},
            timeout_ms=200,
            priority=30,
            description="Stop dispensing immediately"
        ))

        self.register(CommandSpec(
            name="dispense.pulse",
            group="dispense",
            allowed_operation_modes=[OperationMode.auto],
            allowed_process_modes=[ProcessMode.dispensing],
            payload_schema={
                "open_ms": "int",
                "gap_ms": "int",
                "count": "int"
            },
            timeout_ms=1500,
            priority=25,
            description="Pulse solenoid (open/close cycles)"
        ))

        self.register(CommandSpec(
            name="dispense.set_rate",
            group="dispense",
            allowed_operation_modes=[OperationMode.auto],
            allowed_process_modes=[ProcessMode.dispensing],
            payload_schema={"ml_per_sec": "float"},
            timeout_ms=300,
            priority=20,
            description="Set dynamic dispensing flow rate"
        ))

        # -------------------------------------------------------------
        # MOTION GROUP
        # -------------------------------------------------------------
        self.register(CommandSpec(
            name="motion.track_start",
            group="motion",
            allowed_operation_modes=[OperationMode.auto, OperationMode.semi_auto],
            allowed_process_modes=[ProcessMode.idle, ProcessMode.tracking],
            payload_schema={},
            timeout_ms=500,
            priority=30,
            description="Begin plate tracking"
        ))

        self.register(CommandSpec(
            name="motion.track_stop",
            group="motion",
            allowed_operation_modes=[OperationMode.auto, OperationMode.semi_auto],
            allowed_process_modes=[ProcessMode.tracking, ProcessMode.dispensing],
            payload_schema={},
            timeout_ms=500,
            priority=30,
            description="Stop plate tracking"
        ))

        self.register(CommandSpec(
            name="motion.window_mark",
            group="motion",
            allowed_operation_modes=[OperationMode.auto],
            allowed_process_modes=[ProcessMode.tracking],
            payload_schema={"window_id": "int"},
            timeout_ms=200,
            priority=40,
            description="Mark detected window"
        ))

        self.register(CommandSpec(
            name="motion.window_exit",
            group="motion",
            allowed_operation_modes=[OperationMode.auto],
            allowed_process_modes=[ProcessMode.dispensing, ProcessMode.window_detected],
            payload_schema={"window_id": "int"},
            timeout_ms=200,
            priority=40,
            description="Signal that window has exited"
        ))

        # -------------------------------------------------------------
        # PROGRAM GROUP
        # -------------------------------------------------------------
        self.register(CommandSpec(
            name="program.load",
            group="program",
            allowed_operation_modes=[OperationMode.manual],
            allowed_process_modes=[ProcessMode.idle],
            payload_schema={"program_id": "str"},
            timeout_ms=500,
            priority=50,
            description="Load paint program on edge"
        ))

        self.register(CommandSpec(
            name="program.start",
            group="program",
            allowed_operation_modes=[OperationMode.auto],
            allowed_process_modes=[ProcessMode.idle],
            payload_schema={},
            timeout_ms=500,
            priority=80,
            description="Start active program"
        ))

        self.register(CommandSpec(
            name="program.stop",
            group="program",
            allowed_operation_modes=[OperationMode.auto, OperationMode.semi_auto],
            allowed_process_modes=[ProcessMode.tracking, ProcessMode.dispensing, ProcessMode.refill],
            payload_schema={},
            timeout_ms=300,
            priority=90,
            description="Stop active program"
        ))

        self.register(CommandSpec(
            name="program.next_pass",
            group="program",
            allowed_operation_modes=[OperationMode.auto],
            allowed_process_modes=[ProcessMode.idle, ProcessMode.refill],
            payload_schema={"pass_no": "int"},
            timeout_ms=500,
            priority=50,
            description="Move to next forecast pass"
        ))

        # -------------------------------------------------------------
        # PRESSURE GROUP
        # -------------------------------------------------------------
        self.register(CommandSpec(
            name="pressure.flush",
            group="pressure",
            allowed_operation_modes=[OperationMode.manual, OperationMode.auto],
            allowed_process_modes=[ProcessMode.idle],
            payload_schema={"duration_ms": "int"},
            timeout_ms=2000,
            priority=70,
            description="Flush pressure line"
        ))

        self.register(CommandSpec(
            name="pressure.reprime",
            group="pressure",
            allowed_operation_modes=[OperationMode.manual, OperationMode.auto],
            allowed_process_modes=[ProcessMode.idle],
            payload_schema={},
            timeout_ms=2000,
            priority=70,
            description="Reprime pump"
        ))

        self.register(CommandSpec(
            name="pressure.check",
            group="pressure",
            allowed_operation_modes=[OperationMode.auto, OperationMode.manual],
            allowed_process_modes=[ProcessMode.idle, ProcessMode.dispensing],
            payload_schema={},
            timeout_ms=300,
            priority=60,
            description="Check pressure health"
        ))

        # -------------------------------------------------------------
        # VISION GROUP
        # -------------------------------------------------------------
        self.register(CommandSpec(
            name="vision.capture",
            group="vision",
            allowed_operation_modes=[OperationMode.auto, OperationMode.semi_auto],
            allowed_process_modes=[ProcessMode.tracking, ProcessMode.window_detected],
            payload_schema={},
            timeout_ms=400,
            priority=30,
            description="Capture frame for inspection"
        ))

        self.register(CommandSpec(
            name="vision.start",
            group="vision",
            allowed_operation_modes=[OperationMode.auto],
            allowed_process_modes=[ProcessMode.idle],
            payload_schema={},
            timeout_ms=500,
            priority=40,
            description="Start vision system"
        ))

        self.register(CommandSpec(
            name="vision.stop",
            group="vision",
            allowed_operation_modes=[OperationMode.auto],
            allowed_process_modes=[ProcessMode.tracking, ProcessMode.window_detected],
            payload_schema={},
            timeout_ms=500,
            priority=40,
            description="Stop vision system"
        ))

        # -------------------------------------------------------------
        # SAFETY GROUP
        # -------------------------------------------------------------
        self.register(CommandSpec(
            name="system.emergency_stop",
            group="safety",
            allowed_operation_modes=[
                OperationMode.manual,
                OperationMode.auto,
                OperationMode.semi_auto,
                OperationMode.idle
            ],
            allowed_process_modes=[],
            payload_schema={},
            timeout_ms=100,
            priority=100,
            description="Immediate machine shutdown"
        ))

        self.register(CommandSpec(
            name="system.reset_fault",
            group="safety",
            allowed_operation_modes=[OperationMode.manual],
            allowed_process_modes=[ProcessMode.idle],
            payload_schema={},
            timeout_ms=300,
            priority=100,
            description="Reset machine fault"
        ))

        self.register(CommandSpec(
            name="system.set_mode",
            group="system",
            allowed_operation_modes=[OperationMode.manual],  # only manual can switch
            allowed_process_modes=[ProcessMode.idle],
            payload_schema={"mode": "str"},
            timeout_ms=200,
            priority=5,
            description="Switch operation mode"
        ))



command_registry = CommandRegistry()
