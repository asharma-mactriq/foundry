# app/program/strategies/time_based.py

from .base_strategy import DispenseStrategy


class TimeBasedStrategy(DispenseStrategy):

    def __init__(self, open_ms: int):
        self.open_ms = open_ms
        self.fired = False

    def reset(self):
        self.fired = False

    def on_gap_enter(self, ctx):
        if self.fired:
            return

        ctx.executor.send_command({
            "name": "dispense.open",
            "payload": {"open_ms": self.open_ms}
        })

        self.fired = True

    def on_tick(self, ctx):
        pass

    def on_gap_exit(self, ctx):
        self.fired = False