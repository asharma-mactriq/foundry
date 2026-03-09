import time
from app.state.program_state import program_state, ProgramPhase
from app.state.machine_state import machine_state_manager
from app.core import clock

class PressureOrchestrator:

    def __init__(self):
        self.executor = None
        self.last_pressurise_ts = 0
        self.dispense_count = 0

    def notify_dispense(self):
        self.dispense_count += 1

    def process(self):

        if not self.executor:
            return

        if self.executor.is_busy():
            return

        ps = program_state
        now = clock.mono()

        # Only maintain pressure during normal operation
        if ps.phase not in (
            ProgramPhase.READY,
            ProgramPhase.RUNNING,
        ):
            return

        # prevent spam if command just issued
        if now - self.last_pressurise_ts < 5:
            return

        # idle refresh
        if now - self.last_pressurise_ts > 20:
            self._pressurise()
            return

        # refresh after several dispenses
        if self.dispense_count >= 10:
            self._pressurise()

    def _pressurise(self):

        print("[PRESSURE] Maintaining pressure")

        self.executor.send_command({
            "name": "pot.pressurise",
            "payload": {"open_ms": 2000}
        })

        self.last_pressurise_ts = clock.mono()
        self.dispense_count = 0


pressure_orchestrator = PressureOrchestrator()