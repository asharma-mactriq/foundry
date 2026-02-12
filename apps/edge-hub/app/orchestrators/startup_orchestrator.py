from app.state.system_state import system_state, SystemPhase
from app.state.material_state import material_state_manager
from app.state.machine_state import machine_state_manager
from app.commands.helpers import create_and_queue_command

TARGET_PRESSURE = 1.8
MIN_POT_VOLUME = 2.0

class StartupOrchestrator:
    def process(self):
        ms = machine_state_manager.state
        mat = material_state_manager.state

        # Already ready → nothing to do
        if system_state.phase == SystemPhase.READY:
            return

        # Transition BOOTING → INIT
        if system_state.phase == SystemPhase.BOOTING:
            system_state.set_phase(SystemPhase.INIT, "first telemetry")

        # -------- INIT LOGIC --------

        # 1. Ensure pot has paint
        if mat.estimated_pot_volume_ml < MIN_POT_VOLUME:
            create_and_queue_command(
                name="refill.start",
                payload={"duration_ms": 3000}
            )
            return

        # 2. Ensure pressure
        # if ms.pressure < TARGET_PRESSURE:
        #     create_and_queue_command(
        #         name="pressure.reprime",
        #         payload={"duration_ms": 3000, "threshold": TARGET_PRESSURE - 0.2}
        #     )
        #     return

        # 3. Prime dispense line (into waste tray)
        if not mat.dispense_line_primed:
            create_and_queue_command(
                name="dispense.open",
                payload={"open_ms": 200}
            )
            mat.dispense_line_primed = True
            return

        # 4. READY
        system_state.set_phase(SystemPhase.READY, "startup complete")

startup_orchestrator = StartupOrchestrator()
