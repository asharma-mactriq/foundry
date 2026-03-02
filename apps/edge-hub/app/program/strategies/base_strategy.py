# app/program/strategies/base_strategy.py

from abc import ABC, abstractmethod


class DispenseContext:
    def __init__(self, executor, material_state, machine_state, profile):
        self.executor = executor
        self.material_state = material_state
        self.machine_state = machine_state
        self.profile = profile


class DispenseStrategy(ABC):

    @abstractmethod
    def reset(self):
        pass

    @abstractmethod
    def on_gap_enter(self, ctx: DispenseContext):
        pass

    @abstractmethod
    def on_tick(self, ctx: DispenseContext):
        pass

    @abstractmethod
    def on_gap_exit(self, ctx: DispenseContext):
        pass