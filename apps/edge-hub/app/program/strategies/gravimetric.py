# app/program/strategies/gravimetric.py

from .base_strategy import DispenseStrategy


class GravimetricStrategy(DispenseStrategy):

    STOP_MARGIN_KG = 0.003  # 3g safety margin

    def __init__(self, target_kg: float):
        self.target_kg = target_kg
        self.start_weight = None
        self.dispensing = False

    def reset(self):
        self.start_weight = None
        self.dispensing = False

    def on_gap_enter(self, ctx):
        if self.dispensing:
            return

        self.start_weight = ctx.material_state.current_pot_kg

        ctx.executor.send_command({
            "name": "dispense.start",
            "payload": {}
        })

        self.dispensing = True

    def on_tick(self, ctx):
        if not self.dispensing:
            return

        current = ctx.material_state.current_pot_kg
        dispensed = self.start_weight - current

        if dispensed >= (self.target_kg - self.STOP_MARGIN_KG):
            ctx.executor.send_command({
                "name": "dispense.stop",
                "payload": {}
            })
            self.dispensing = False

    def on_gap_exit(self, ctx):
        if self.dispensing:
            ctx.executor.send_command({
                "name": "dispense.stop",
                "payload": {}
            })
            self.dispensing = False