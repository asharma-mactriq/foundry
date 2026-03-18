from abc import ABC, abstractmethod


class GapPolicy(ABC):

    @abstractmethod
    def reset(self):
        pass

    @abstractmethod
    def on_gap(self, program, machine) -> bool:
        """
        Return True if this gap should trigger dispense.
        """
        pass