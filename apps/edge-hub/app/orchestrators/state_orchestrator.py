from app.state.machine_state import machine_state_manager
from app.state.program_state import program_state
from app.services.rule_engine import get_rule_engine
from app.orchestrators.material_orchestrator import material_orchestrator
from app.orchestrators.startup_orchestrator import startup_orchestrator
from app.state.system_state import system_state, SystemPhase

class StateOrchestrator:
    def process(self, telemetry):
        # 1. Update machine state from incoming telemetry
        ms = machine_state_manager.apply_telemetry(telemetry)
        mat = material_orchestrator.process_telemetry(telemetry)
        ps = program_state

        #  NEW: always run startup orchestrator first
        startup_orchestrator.process()

        #  Block program logic until READY
        if system_state.phase != SystemPhase.READY:
            return ms, ps
        
        self._evaluate_rules(telemetry, ms, ps, mat)

        if not ps.is_running():
            return ms, ps
        
        # --------------------------------------
        # PASS ENTER (gap: 0 → 1)
        # --------------------------------------
        if ms.gap_transition == "enter":
            pid = ps.new_pass()
            print(f"[STATE] Pass {pid} ENTER detected")

        # --------------------------------------
        # PASS STABLE
        # --------------------------------------
        if ms.plate_stable:
            pid = ps.current_pass
            if pid > 0:
                p = ps.passes.get(pid)
                if p and p.stable_ts == 0:
                    ps.mark_stable(pid)
                    print(f"[STATE] Pass {pid} STABLE detected")

        # --------------------------------------
        # PASS EXIT (gap: 1 → 0)
        # --------------------------------------
        if ms.gap_transition == "exit":
            pid = ps.current_pass
            if pid > 0:
                ps.mark_exit(pid)
                print(f"[STATE] Pass {pid} EXIT detected")

        # --------------------------------------
        # FINALLY: RUN RULE ENGINE
        # --------------------------------------
       

        return ms, ps


    # ------------------------------------------
    # INTERNAL: rule evaluation entry point
    # ------------------------------------------
    def _evaluate_rules(self, raw, ms, ps, mat):
        rule_engine = get_rule_engine()
        fired = rule_engine.evaluate_all(
            raw=raw,
            machine=ms,
            program=ps,
            material=mat,

            # machine=ms.__dict__,
            # program=ps.serialize(),
            # material=mat.__dict__,
        )
        if fired:
            print("[RULES] Fired:", fired)


state_orchestrator = StateOrchestrator()
