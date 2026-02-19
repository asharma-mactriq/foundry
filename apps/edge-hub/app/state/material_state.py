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

    current_pot_kg: float = 0.0
    estimated_dispensed_kg: float = 0.0

    pot_min_kg: float = 0.0
    res_min_kg: float = 0.0

    paint_confidence: str = "UNKNOWN"      # HIGH | LOW | UNKNOWN
    dispense_confidence: str = "UNKNOWN"   # HIGH | LOW | UNKNOWN
    
    dispensing_active: bool = False
    dispense_start_ts: float = 0.0
    last_flow_ts: float = 0.0   # ✅ REQUIRED

    last_event: str = None
    last_event_ts: float = 0.0

        # Pot fill tracking
    pot_fill_target_kg: float = 0.0
    pot_fill_start_weight: float = 0.0
    pot_fill_start_ts: float = 0.0

    # Pressurisation tracking
    pressurise_target_bar: float = 0.8
    pressurise_start_ts: float = 0.0

    # Line priming — weight-based detection
    line_prime_start_weight: float = 0.0
    line_prime_start_ts: float = 0.0
    line_primed: bool = False

    # Mid-run refill tracking
    mid_refill_count: int = 0
    last_mid_refill_ts: float = 0.0


class MaterialStateManager:
    def __init__(self):
        self.state = MaterialState()

material_state_manager = MaterialStateManager()
