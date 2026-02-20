import time
from app.services.command_executor import CommandExecutor
from app.state.material_state import material_state_manager
from app.state.program_state import program_state
from app.config.paint_profile import PaintProfile


class MidRefillOrchestrator:

    def __init__(self, executor: CommandExecutor):
        self.executor = executor
        self.profile: PaintProfile = None
        self.state = "IDLE"

        self.weight_before = 0.0
        self.settle_start = 0.0

    # ──────────────────────────────────────────────
    def reset(self):
        self.state = "IDLE"

    # ──────────────────────────────────────────────
    def begin(self, profile: PaintProfile):
        if self.state != "IDLE":
            return

        mat = material_state_manager.state
        self.profile = profile
        self.weight_before = mat.current_pot_kg

        print("[MID_REFILL] Pressure-assisted refill begin")
        program_state.begin_mid_refill()

        self.state = "DEPRESSURISE_POT"

    # ──────────────────────────────────────────────
    def process(self):

        if self.executor.is_busy():
            return

        mat = material_state_manager.state
        p = self.profile

        # 1️⃣ Depressurise pot
        if self.state == "DEPRESSURISE_POT":
            print("[MID_REFILL] Depressurising pot")
            self.executor.send_command({"name": "pot.depressurise", "payload": {}})
            self.state = "PRESSURISE_RES"
            return

        # 2️⃣ Pressurise reservoir
        if self.state == "PRESSURISE_RES":
            print("[MID_REFILL] Pressurising reservoir")
            self.executor.send_command({
                "name": "res.pressurise",
                "payload": {"open_ms": int(p.pressurise_open_s * 5000)}
            })
            self.state = "OPEN_INLET"
            return

        # 3️⃣ Open inlet
        if self.state == "OPEN_INLET":
            print("[MID_REFILL] Opening paint inlet")
            self.executor.send_command({
                "name": "pot.fill_start",
                "payload": {"target_kg": p.mid_refill_target_kg}
            })
            self.state = "WAIT_TARGET"
            return

        # 4️⃣ Wait for target
        if self.state == "WAIT_TARGET":
            # if mat.current_pot_kg >= p.mid_refill_target_kg:
            print("[MID_REFILL] Target reached")
            self.executor.send_command({
                "name": "pot.fill_stop",
                "payload": {}
            })
            self.settle_start = time.time()
            self.state = "SETTLING"
            return

        # 5️⃣ Settling
        if self.state == "SETTLING":
            if time.time() - self.settle_start < p.mid_refill_settle_s:
                return

            gain = mat.current_pot_kg - self.weight_before
            print(f"[MID_REFILL] Gain after settle: {gain:.3f}kg")

            self.state = "DEPRESSURISE_RES"
            return

        # 6️⃣ Depressurise reservoir
        if self.state == "DEPRESSURISE_RES":
            print("[MID_REFILL] Depressurising reservoir")
            self.executor.send_command({"name": "res.depressurise", "payload": {}})
            self.state = "REPRESSURISE_POT"
            return

        # 7️⃣ Re-pressurise pot
        if self.state == "REPRESSURISE_POT":
            print("[MID_REFILL] Re-pressurising pot")
            self.executor.send_command({
                "name": "pot.pressurise",
                "payload": {"open_ms": int(p.pressurise_open_s * 1000)}
            })
            self.state = "COMPLETE"
            return

        # 8️⃣ Complete
        if self.state == "COMPLETE":
            print("[MID_REFILL] Refill complete → RUNNING")
            self.state = "IDLE"
            program_state.on_mid_refill_done()
