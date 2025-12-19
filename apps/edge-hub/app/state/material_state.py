# app/state/material_state.py
from dataclasses import dataclass
import time

@dataclass
class MaterialState:
    reservoir_pressure: float = 0.0
    reservoir_has_paint: bool = True

    pot_pressure: float = 0.0
    pot_filled: bool = False
    pot_fill_ts: float = 0.0

    fill_line_primed: bool = False
    dispense_line_primed: bool = False

    estimated_pot_volume_ml: float = 0.0
    estimated_dispensed_ml: float = 0.0

    dispensing_active: bool = False
    dispense_start_ts: float = 0.0

    last_event: str = None
    last_event_ts: float = 0.0


class MaterialStateManager:
    def __init__(self):
        self.state = MaterialState()

material_state_manager = MaterialStateManager()
