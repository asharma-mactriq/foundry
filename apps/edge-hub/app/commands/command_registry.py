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

    def is_allowed_in_mode(self, mode_state) -> bool:
        """
        Empty list = allowed in ALL modes (unrestricted).
        Non-empty list = must match one of the listed modes.
        """
        operation = (
            getattr(mode_state, "operation", None)
            or mode_state.get("operation")
        )
        process = (
            getattr(mode_state, "process", None)
            or mode_state.get("process")
        )
        if self.allowed_operation_modes:
            if operation not in self.allowed_operation_modes:
                return False
        if self.allowed_process_modes:
            if process not in self.allowed_process_modes:
                return False
        return True

    def check_preconditions(self, device_state):
        for fn in self.preconditions:
            ok, reason = fn(device_state)
            if not ok:
                return False, reason
        return True, None


class CommandRegistry:

    def __init__(self):
        self.commands: Dict[str, CommandSpec] = {}
        self._load_defaults()

    def register(self, spec: CommandSpec):
        if spec.name in self.commands:
            raise ValueError(f"Duplicate command: {spec.name}")
        self.commands[spec.name] = spec

    def get(self, name: str) -> CommandSpec:
        if name not in self.commands:
            raise KeyError(f"Unknown command: {name}")
        return self.commands[name]

    def list_all(self):
        return list(self.commands.values())

    def _load_defaults(self):
        from app.modes.mode_types import OperationMode, ProcessMode

        # ── PROGRAM ───────────────────────────────────────────────
        # program.load: manual only (operator triggered, firmware receives)
        self.register(CommandSpec(
            name="program.load",
            group="program",
            allowed_operation_modes=[OperationMode.manual],
            allowed_process_modes=[ProcessMode.idle],
            payload_schema={"program_id": "str"},
            timeout_ms=500,
            priority=50,
            description="Load paint program config on firmware"
        ))

        # program.stop: UNRESTRICTED — safety command, must always execute
        # Empty lists = allowed in all modes and all process phases
        self.register(CommandSpec(
            name="program.stop",
            group="program",
            allowed_operation_modes=[],   # unrestricted
            allowed_process_modes=[],     # unrestricted
            payload_schema={},
            timeout_ms=300,
            priority=100,
            description="Stop active program — always allowed regardless of mode"
        ))

        # ── STARTUP ───────────────────────────────────────────────
        self.register(CommandSpec(
            name="startup.sequence",
            group="program",
            allowed_operation_modes=[OperationMode.manual, OperationMode.auto],
            allowed_process_modes=[ProcessMode.idle],
            payload_schema={},
            timeout_ms=5000,
            priority=85,
            description="Firmware hardware initialisation sequence"
        ))

        self.register(CommandSpec(
            name="res.pressurise",
            group="reservoir",
            allowed_operation_modes=[],
            allowed_process_modes=[],
            payload_schema={"open_ms": "int"},
            timeout_ms=15000,
            priority=80,
            description="Pressurise reservoir air inlet"
        ))

        self.register(CommandSpec(
            name="res.depressurise",
            group="reservoir",
            allowed_operation_modes=[],
            allowed_process_modes=[],
            payload_schema={},
            timeout_ms=10000,
            priority=80,
            description="Vent reservoir pressure"
        ))


        # ── POT FILL ──────────────────────────────────────────────
        # Opens paint_inlet valve. Firmware holds it open until told to stop.
        # Edge hub watches weight and sends pot.fill_stop when target reached.
        self.register(CommandSpec(
            name="pot.fill_start",
            group="pot",
            allowed_operation_modes=[],   # unrestricted — needed in multiple phases
            allowed_process_modes=[],
            payload_schema={"target_kg": "float"},
            timeout_ms=120000,   # up to 2 min — firmware just opens valve and waits
            priority=75,
            description="Open paint_inlet valve — edge hub closes it via pot.fill_stop"
        ))

        self.register(CommandSpec(
            name="pot.fill_stop",
            group="pot",
            allowed_operation_modes=[],
            allowed_process_modes=[],
            payload_schema={},
            timeout_ms=3000,
            priority=75,
            description="Close paint_inlet valve"
        ))

        # ── PRESSURISATION ────────────────────────────────────────
        # Opens pot_air_in for a fixed duration (ms from payload).
        # Firmware closes it after duration — no sensor gate needed.
        self.register(CommandSpec(
            name="pot.pressurise",
            group="pot",
            allowed_operation_modes=[],
            allowed_process_modes=[],
            payload_schema={"open_ms": "int"},
            timeout_ms=30000,
            priority=80,
            description="Open pot_air_in for open_ms milliseconds (time-based)"
        ))

        self.register(CommandSpec(
            name="pot.depressurise",
            group="pot",
            allowed_operation_modes=[],
            allowed_process_modes=[],
            payload_schema={},
            timeout_ms=10000,
            priority=80,
            description="Open pot_air_out to release pot pressure"
        ))

        # ── LINE PRIMING ──────────────────────────────────────────
        # Opens dispense solenoid for line priming.
        # Different from dispense.open because:
        #   - orchestrator applies different completion logic (rate-of-change)
        #   - firmware workflow can emit line_prime events for logging
        self.register(CommandSpec(
            name="line.prime_start",
            group="line",
            allowed_operation_modes=[],
            allowed_process_modes=[],
            payload_schema={"timeout_ms": "int"},
            timeout_ms=200000,   # generous — orchestrator times out first
            priority=78,
            description="Open dispense valve for line priming — edge hub monitors weight drop"
        ))

        self.register(CommandSpec(
            name="line.prime_stop",
            group="line",
            allowed_operation_modes=[],
            allowed_process_modes=[],
            payload_schema={},
            timeout_ms=2000,
            priority=78,
            description="Close dispense valve after line primed"
        ))

        # ── DISPENSE ──────────────────────────────────────────────
        # Open solenoid for exactly open_ms milliseconds.
        # Firmware handles the timing precisely.
        self.register(CommandSpec(
            name="dispense.open",
            group="dispense",
            allowed_operation_modes=[OperationMode.auto, OperationMode.semi_auto],
            allowed_process_modes=[ProcessMode.dispensing, ProcessMode.window_detected],
            payload_schema={"open_ms": "int"},
            timeout_ms=2000,
            priority=20,
            description="Open dispense solenoid for open_ms ms"
        ))

        self.register(CommandSpec(
            name="dispense.stop",
            group="dispense",
            allowed_operation_modes=[],   # unrestricted — stop must always work
            allowed_process_modes=[],
            payload_schema={},
            timeout_ms=200,
            priority=90,
            description="Close dispense solenoid immediately"
        ))

        # ── SAFETY ────────────────────────────────────────────────
        self.register(CommandSpec(
            name="system.emergency_stop",
            group="safety",
            allowed_operation_modes=[],   # always allowed
            allowed_process_modes=[],
            payload_schema={},
            timeout_ms=100,
            priority=100,
            description="Immediate machine shutdown — closes all valves"
        ))


command_registry = CommandRegistry()

# # app/commands/command_registry.py

# from typing import Dict, List, Callable, Optional
# from app.modes.mode_types import OperationMode, ProcessMode


# class CommandSpec:
#     def __init__(
#         self,
#         name: str,
#         group: str,
#         allowed_operation_modes: Optional[List[OperationMode]] = None,
#         allowed_process_modes: Optional[List[ProcessMode]] = None,
#         payload_schema: Optional[Dict[str, str]] = None,
#         timeout_ms: int = 800,
#         priority: int = 10,
#         preconditions: Optional[List[Callable]] = None,
#         description: str = ""
#     ):
#         self.name = name
#         self.group = group
#         self.allowed_operation_modes = allowed_operation_modes or []
#         self.allowed_process_modes = allowed_process_modes or []
#         self.payload_schema = payload_schema or {}
#         self.timeout_ms = timeout_ms
#         self.priority = priority
#         self.preconditions = preconditions or []
#         self.description = description

#     # -------------------------------------------------------------------
#     def is_allowed_in_mode(self, mode_state):
#         """Support both dict-style and object-style mode_state input."""
#         operation = (
#             getattr(mode_state, "operation", None)
#             or mode_state["operation"]
#         )
#         process = (
#             getattr(mode_state, "process", None)
#             or mode_state["process"]
#         )

#         # Check operation mode
#         if self.allowed_operation_modes:
#             if operation not in self.allowed_operation_modes:
#                 return False

#         # Check process mode
#         if self.allowed_process_modes:
#             if process not in self.allowed_process_modes:
#                 return False

#         return True

#     # -------------------------------------------------------------------
#     def check_preconditions(self, device_state):
#         for fn in self.preconditions:
#             ok, reason = fn(device_state)
#             if not ok:
#                 return False, reason
#         return True, None


# # =====================================================================
# # COMMAND REGISTRY
# # =====================================================================

# class CommandRegistry:

#     def __init__(self):
#         self.commands: Dict[str, CommandSpec] = {}
#         self._load_defaults()

#     def register(self, spec: CommandSpec):
#         if spec.name in self.commands:
#             raise ValueError("Duplicate command registered")
#         self.commands[spec.name] = spec

#     def get(self, name: str) -> CommandSpec:
#         if name not in self.commands:
#             raise KeyError(f"Unknown command: {name}")
#         return self.commands[name]

#     def list_all(self):
#         return list(self.commands.values())

#     # =================================================================
#     # ALL MACHINE COMMANDS (FINAL)
#     # =================================================================
#     def _load_defaults(self):
#         from app.modes.mode_types import OperationMode, ProcessMode

#         # -------------------------------------------------------------
#         # DISPENSE GROUP
#         # -------------------------------------------------------------
#         self.register(CommandSpec(
#             name="dispense.open",
#             group="dispense",
#             allowed_operation_modes=[OperationMode.auto, OperationMode.semi_auto],
#             allowed_process_modes=[ProcessMode.dispensing, ProcessMode.window_detected],
#             payload_schema={"open_ms": "int"},
#             timeout_ms=800,
#             priority=20,
#             description="Open solenoid for X milliseconds"
#         ))

#         self.register(CommandSpec(
#             name="dispense.stop",
#             group="dispense",
#             allowed_operation_modes=[OperationMode.auto, OperationMode.semi_auto],
#             allowed_process_modes=[ProcessMode.dispensing],
#             payload_schema={},
#             timeout_ms=200,
#             priority=30,
#             description="Stop dispensing immediately"
#         ))

#         # self.register(CommandSpec(
#         #     name="dispense.pulse",
#         #     group="dispense",
#         #     allowed_operation_modes=[OperationMode.auto],
#         #     allowed_process_modes=[ProcessMode.dispensing],
#         #     payload_schema={
#         #         "open_ms": "int",
#         #         "gap_ms": "int",
#         #         "count": "int"
#         #     },
#         #     timeout_ms=1500,
#         #     priority=25,
#         #     description="Pulse solenoid (open/close cycles)"
#         # ))

#         # self.register(CommandSpec(
#         #     name="dispense.set_rate",
#         #     group="dispense",
#         #     allowed_operation_modes=[OperationMode.auto],
#         #     allowed_process_modes=[ProcessMode.dispensing],
#         #     payload_schema={"ml_per_sec": "float"},
#         #     timeout_ms=300,
#         #     priority=20,
#         #     description="Set dynamic dispensing flow rate"
#         # ))

#         # self.register(CommandSpec(
#         #     name="refill.start",
#         #     group="refill",
#         #     allowed_operation_modes=[OperationMode.auto, OperationMode.manual],
#         #     allowed_process_modes=[
#         #         ProcessMode.idle,
#         #         ProcessMode.refill,
#         #         ProcessMode.dispensing,
#         #         ProcessMode.tracking
#         #     ],
#         #     # allowed_process_modes=[ProcessMode.idle, ProcessMode.refill],
#         #     payload_schema={"duration_ms": "int"},
#         #     priority=60
#         # ))


#         # Inside app/commands/command_registry.py -> _load_defaults()

#         self.register(CommandSpec(
#             name="startup.sequence",
#             group="program",
#             # Allow in manual (since we just loaded) or auto
#             allowed_operation_modes=[OperationMode.manual, OperationMode.auto],
#             allowed_process_modes=[ProcessMode.idle],
#             payload_schema={},
#             timeout_ms=5000, # Give it time to run physical steps
#             priority=85,
#             description="Initializes hardware after program load"
#         ))

#         # Demo Run Command to be shown on edge ui

#         self.register(CommandSpec(
#             name="demo.run",
#             group="demo",
#             allowed_operation_modes=[OperationMode.auto],
#             allowed_process_modes=[ProcessMode.idle],
#             payload_schema={
#                 "runs": "int",
#                 "pressure": "str"  # "0.6" or "0.8"
#             },
#             timeout_ms=1000,
#             priority=90,
#             description="Run demo pressurise + dispense cycle"
#         ))



#         # -------------------------------------------------------------
#         # MOTION GROUP
#         # -------------------------------------------------------------
#         # self.register(CommandSpec(
#         #     name="motion.track_start",
#         #     group="motion",
#         #     allowed_operation_modes=[OperationMode.auto, OperationMode.semi_auto],
#         #     allowed_process_modes=[ProcessMode.idle, ProcessMode.tracking],
#         #     payload_schema={},
#         #     timeout_ms=500,
#         #     priority=30,
#         #     description="Begin plate tracking"
#         # ))

#         # self.register(CommandSpec(
#         #     name="motion.track_stop",
#         #     group="motion",
#         #     allowed_operation_modes=[OperationMode.auto, OperationMode.semi_auto],
#         #     allowed_process_modes=[ProcessMode.tracking, ProcessMode.dispensing],
#         #     payload_schema={},
#         #     timeout_ms=500,
#         #     priority=30,
#         #     description="Stop plate tracking"
#         # ))

#         # self.register(CommandSpec(
#         #     name="motion.window_mark",
#         #     group="motion",
#         #     allowed_operation_modes=[OperationMode.auto],
#         #     allowed_process_modes=[ProcessMode.tracking],
#         #     payload_schema={"window_id": "int"},
#         #     timeout_ms=200,
#         #     priority=40,
#         #     description="Mark detected window"
#         # ))

#         # self.register(CommandSpec(
#         #     name="motion.window_exit",
#         #     group="motion",
#         #     allowed_operation_modes=[OperationMode.auto],
#         #     allowed_process_modes=[ProcessMode.dispensing, ProcessMode.window_detected],
#         #     payload_schema={"window_id": "int"},
#         #     timeout_ms=200,
#         #     priority=40,
#         #     description="Signal that window has exited"
#         # ))



#         # -------------------------------------------------------------
#         # PROGRAM GROUP
#         # -------------------------------------------------------------
#         self.register(CommandSpec(
#             name="program.load",
#             group="program",
#             allowed_operation_modes=[OperationMode.manual],
#             allowed_process_modes=[ProcessMode.idle],
#             payload_schema={"program_id": "str"},
#             timeout_ms=500,
#             priority=50,
#             description="Load paint program on edge"
#         ))

#         self.register(CommandSpec(
#             name="program.start",
#             group="program",
#             allowed_operation_modes=[OperationMode.auto],
#             allowed_process_modes=[ProcessMode.idle],
#             payload_schema={},
#             timeout_ms=500,
#             priority=80,
#             description="Start active program"
#         ))

#         self.register(CommandSpec(
#             name="program.stop",
#             group="program",
#             allowed_operation_modes=[OperationMode.auto, OperationMode.semi_auto],
#             allowed_process_modes=[ProcessMode.tracking, ProcessMode.dispensing, ProcessMode.refill],
#             payload_schema={},
#             timeout_ms=300,
#             priority=90,
#             description="Stop active program"
#         ))

#         # self.register(CommandSpec(
#         #     name="program.next_pass",
#         #     group="program",
#         #     allowed_operation_modes=[OperationMode.auto],
#         #     allowed_process_modes=[ProcessMode.idle, ProcessMode.refill],
#         #     payload_schema={"pass_no": "int"},
#         #     timeout_ms=500,
#         #     priority=50,
#         #     description="Move to next forecast pass"
#         # ))


#         # -------------------------------------------------------------
#         # PRESSURE GROUP
#         # -------------------------------------------------------------
#         self.register(CommandSpec(
#             name="pressure.flush",
#             group="pressure",
#             allowed_operation_modes=[OperationMode.manual, OperationMode.auto],
#             allowed_process_modes=[ProcessMode.idle],
#             payload_schema={"duration_ms": "int"},
#             timeout_ms=2000,
#             priority=70,
#             description="Flush pressure line"
#         ))

#         self.register(CommandSpec(
#             name="pressure.reprime",
#             group="pressure",
#             allowed_operation_modes=[OperationMode.manual, OperationMode.auto],
#             allowed_process_modes=[ProcessMode.idle],
#             payload_schema={},
#             timeout_ms=2000,
#             priority=70,
#             description="Reprime pump"
#         ))

#         # self.register(CommandSpec(
#         #     name="pressure.check",
#         #     group="pressure",
#         #     allowed_operation_modes=[OperationMode.auto, OperationMode.manual],
#         #     allowed_process_modes=[ProcessMode.idle, ProcessMode.dispensing],
#         #     payload_schema={},
#         #     timeout_ms=300,
#         #     priority=60,
#         #     description="Check pressure health"
#         # ))

#         # POT FILL
#         self.register(CommandSpec(
#             name="pot.fill_start",
#             group="pot",
#             allowed_operation_modes=[OperationMode.auto, OperationMode.manual],
#             allowed_process_modes=[],   # empty = all phases
#             payload_schema={"target_kg": "float"},
#             timeout_ms=30000,
#             priority=75,
#             description="Open paint_inlet valve to fill pot from reservoir"
#         ))

#         self.register(CommandSpec(
#             name="pot.fill_stop",
#             group="pot",
#             allowed_operation_modes=[OperationMode.auto, OperationMode.manual],
#             allowed_process_modes=[],
#             payload_schema={},
#             timeout_ms=3000,
#             priority=75,
#             description="Close paint_inlet valve"
#         ))

#         # PRESSURISATION
#         self.register(CommandSpec(
#             name="pot.pressurise",
#             group="pot",
#             allowed_operation_modes=[OperationMode.auto, OperationMode.manual],
#             allowed_process_modes=[],
#             payload_schema={"target_bar": "float"},
#             timeout_ms=15000,
#             priority=80,
#             description="Open pot_air_in until target pressure reached"
#         ))

#         self.register(CommandSpec(
#             name="pot.depressurise",
#             group="pot",
#             allowed_operation_modes=[OperationMode.auto, OperationMode.manual],
#             allowed_process_modes=[],
#             payload_schema={},
#             timeout_ms=5000,
#             priority=80,
#             description="Open pot_air_out to release pressure"
#         ))

#         # LINE PRIMING
#         self.register(CommandSpec(
#             name="line.prime_start",
#             group="line",
#             allowed_operation_modes=[OperationMode.auto, OperationMode.manual],
#             allowed_process_modes=[],
#             payload_schema={"timeout_ms": "int"},
#             timeout_ms=60000,   # line length unknown, be generous
#             priority=78,
#             description="Open dispense valve to push paint through line until exit"
#         ))

#         self.register(CommandSpec(
#             name="line.prime_stop",
#             group="line",
#             allowed_operation_modes=[OperationMode.auto, OperationMode.manual],
#             allowed_process_modes=[],
#             payload_schema={},
#             timeout_ms=2000,
#             priority=78,
#             description="Close dispense valve after line is primed"
#         ))

#         # Fix program.stop — remove all mode restrictions so rules can always fire it
#         self.register(CommandSpec(
#             name="program.stop",
#             group="program",
#             allowed_operation_modes=[],   # empty = unrestricted
#             allowed_process_modes=[],     # empty = unrestricted
#             payload_schema={},
#             timeout_ms=300,
#             priority=90,
#             description="Stop active program — always allowed"
#         ))

#         # -------------------------------------------------------------
#         # SAFETY GROUP
#         # -------------------------------------------------------------
#         self.register(CommandSpec(
#             name="system.emergency_stop",
#             group="safety",
#             allowed_operation_modes=[
#                 OperationMode.manual,
#                 OperationMode.auto,
#                 OperationMode.semi_auto,
#                 OperationMode.idle
#             ],
#             allowed_process_modes=[],
#             payload_schema={},
#             timeout_ms=100,
#             priority=100,
#             description="Immediate machine shutdown"
#         ))

#         self.register(CommandSpec(
#             name="system.reset_fault",
#             group="safety",
#             allowed_operation_modes=[OperationMode.manual],
#             allowed_process_modes=[ProcessMode.idle],
#             payload_schema={},
#             timeout_ms=300,
#             priority=100,
#             description="Reset machine fault"
#         ))

#         self.register(CommandSpec(
#             name="system.set_mode",
#             group="system",
#             allowed_operation_modes=[OperationMode.manual],  # only manual can switch
#             allowed_process_modes=[ProcessMode.idle],
#             payload_schema={"mode": "str"},
#             timeout_ms=200,
#             priority=5,
#             description="Switch operation mode"
#         ))



# command_registry = CommandRegistry()
