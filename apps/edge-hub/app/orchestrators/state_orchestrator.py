# app/orchestrators/state_orchestrator.py

from app.state.machine_state import machine_state_manager
from app.state.program_state import program_state, ProgramPhase
from app.services.rule_engine import get_rule_engine
from app.orchestrators.material_orchestrator import material_orchestrator
from app.orchestrators.startup_orchestrator import startup_orchestrator
from app.state.system_state import system_state, SystemPhase
from app.core import clock
from app.modes.mode_manager import mode_manager
from app.modes.mode_types import ProcessMode
from app.program.program_engine import program_engine

class StateOrchestrator:

    def __init__(self):
        self.executor = None

    def set_executor(self, executor):
        self.executor = executor
        startup_orchestrator.executor = executor

    def process(self, telemetry):

        now = clock.mono()

        if not self.executor:
            print("[STATE_ORCH] executor not injected yet")
            return None, None


        # 1. Update machine state
        ms = machine_state_manager.apply_telemetry(telemetry)
        ps = program_state

        # ── Telemetry watchdog ────────────────────────────────────
        if ms.last_update_ts is not None:
            if (now - ms.last_update_ts) > 3.0:
                print("[WATCHDOG] Telemetry timeout")
                system_state.set_phase(SystemPhase.FAULT, "telemetry_timeout")
                return ms, ps

        # 2. Material state
        mat = material_orchestrator.process_telemetry(telemetry)
        
        startup_orchestrator.process()

        # 3. System startup (booting → init → ready)
        self._process_system_startup()

        # Block program logic until system is READY
        if system_state.phase != SystemPhase.READY:
            return ms, ps

        # 4. Rules (only in RUNNING or READY — rule engine gates itself)
        self._evaluate_rules(telemetry, ms, ps, mat)

        # 5. Program not active — nothing else to do
        if not ps.is_active():
            return ms, ps

        # 6. Gap/plate detection (only meaningful in RUNNING)
        # if ps.phase in (ProgramPhase.READY, ProgramPhase.RUNNING):
        #     self._process_gap_events(ms, ps, now)

        # return ms, ps

        # 6. Gap/plate detection
        if ps.phase in (ProgramPhase.READY, ProgramPhase.RUNNING):
            self._process_gap_events(ms, ps, now)

        # 7. Program Engine (dispense logic)

        if program_engine:
            program_engine.on_event(ms, ps)

        # pressure_orchestrator.process()

        return ms, ps

    # ──────────────────────────────────────────────────────────────
    def _process_system_startup(self):
        """Transition system from BOOTING → INIT → READY on first telemetry."""
        if system_state.phase == SystemPhase.BOOTING:
            system_state.set_phase(SystemPhase.INIT, "first telemetry")

        if system_state.phase == SystemPhase.INIT:
            # For now: go to READY immediately.
            # Add hardware checks here if needed (e.g. firmware ping response).
            system_state.set_phase(SystemPhase.READY, "startup complete")

    # ──────────────────────────────────────────────────────────────
    def _process_gap_events(self, ms, ps, now):
        """Detect plate enter/stable/exit and update program state."""

        # PASS ENTER (gap: 0 → 1)
        if ms.gap_transition == "enter":
            pid = ps.new_pass()
            # if ps.last_event is None:
            #     ps.last_event = "pass_enter"
            print(f"[STATE] Pass {pid} ENTER")

        # PASS STABLE
        # if ms.gap == 1 and ms.plate_stable:
        if ms.last_event == "plate_stable":
            # from app.modes.mode_types import ProcessMode
            mode_manager.set_process(ProcessMode.window_detected)

            pid = ps.current_pass
            if pid > 0:
                p = ps.passes.get(pid)
                if p and p.stable_ts == 0:
                    ps.mark_stable(pid)
                    # if ps.last_event is None:
                    #     ps.last_event = "pass_stable"
                    print(f"[STATE] Pass {pid} STABLE")

        # JAM DETECTION
        if ms.gap == 1 and ms.plate_stable:
            
            elapsed = now - ms.plate_stable_since
            if elapsed > 60.0:
                print("[JAM] Plate stuck too long")
                program_state.abort("plate_stuck")
                system_state.set_phase(SystemPhase.FAULT, "plate_stuck")
                return

        # PASS EXIT (gap: 1 → 0)
        if ms.gap_transition == "exit":
            mode_manager.set_process(ProcessMode.tracking)
            pid = ps.current_pass
            if pid > 0:
                ps.mark_exit(pid)
                # if ps.last_event is None:
                #     ps.last_event = "pass_exit"
                print(f"[STATE] Pass {pid} EXIT")

        ms.last_event = None

    # ──────────────────────────────────────────────────────────────
    def _evaluate_rules(self, raw, ms, ps, mat):
        rule_engine = get_rule_engine()
        fired = rule_engine.evaluate_all(
            raw=raw,
            machine=ms,
            program=ps,
            material=mat,
        )
        if fired:
            print("[RULES] Fired:", fired)


state_orchestrator = StateOrchestrator()
