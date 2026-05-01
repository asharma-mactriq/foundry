# app/config/paint_profile.py

from dataclasses import dataclass
from typing import Optional


@dataclass
class PaintProfile:
    # ── Identity ──────────────────────────────────────────────────
    name: str = "default"
    description: str = ""

    # ── Pot Fill ──────────────────────────────────────────────────
    pot_fill_target_kg: float = 3.5
    pot_fill_flow_start_timeout_s: float = 8.0
    pot_fill_total_timeout_s: float = 60.0
    pot_fill_min_gain_kg: float = 0.05
    pot_fill_settle_s: float = 2.0
    pot_fill_open_time_s: float = 6.0

    # ── Pressurisation ────────────────────────────────────────────
    pressurise_open_s: float = 5.0
    pressurise_max_open_s: float = 25.0

    # ── Line Priming ──────────────────────────────────────────────
    line_prime_min_time_s: float = 5.0
    line_prime_timeout_s: float = 60.0
    line_prime_max_drain_kg: float = 1.2
    line_prime_nozzle_crack_rate_kg_s: float = 1.0
    line_prime_stable_confirm_s: float = 0.5
    line_prime_rate_window_s: float = 0.05
    line_prime_mode: str = "open_pipe"
    line_prime_line_volume_kg: float = 0.25

    # ── Dispense ──────────────────────────────────────────────────
    dispense_open_ms: int = 1000
    nozzle_open_lag_ms: int = 50
    nozzle_close_lag_ms: int = 50
    inter_plate_maintain_open_ms: int = 0

    @property
    def effective_dispense_ms(self) -> int:
        return max(0, self.dispense_open_ms - self.nozzle_open_lag_ms - self.nozzle_close_lag_ms)

    # ── Pressure Model (time-based, no sensor) ────────────────────
    #
    # Physical measurements:
    #   Working range:        0.28 – 0.35 MPa
    #   Charge time (full pot, from 0 to range): 8–10s → midpoint 9s
    #   Charge rate:          0.35 / 9s = 0.0389 MPa/s
    #   Idle bleed rate:      0.35 MPa over 5 min = 0.00117 MPa/s
    #     → takes 60s to bleed from 0.35 → 0.28 (leaves working range)
    #   Dispense bleed rate:  0.05 MPa/s while solenoid open
    #     → takes 1.4s to bleed from 0.35 → 0.28 during active dispense
    #
    # Strategy:
    #   Maintain estimated_pressure_mpa each tick.
    #   Add charge when pot_air_in is open (charge_rate_mpa_per_s).
    #   Subtract idle bleed or dispense bleed depending on solenoid state.
    #   Fire a top-up pulse when estimated pressure < pressure_low_mpa.
    #   Stop pulse when estimated pressure >= pressure_high_mpa.
    #   Never open pot_air_in and pot_air_out simultaneously.

    # Target pressure band (MPa)
    pressure_low_mpa: float = 0.28       # fire top-up below this
    pressure_high_mpa: float = 0.35      # stop top-up at this

    # How long pot_air_in must be open to go from 0 → pressure_high_mpa
    # at full pot (pressure_model_ref_kg). Measured: 8–10s → 9s midpoint.
    pressure_charge_time_s: float = 25.0

    # Reference fill weight for charge_time measurement (kg)
    pressure_model_ref_kg: float = 3.5

    # Headspace correction: more paint = less headspace = faster charge.
    # charge_rate scales linearly with paint weight.
    # open_s_needed = charge_time_s * (ref_kg / current_kg) * headspace_factor
    # Start at 1.0, increase to 1.2–1.5 if low-fill dispenses are weak.
    pressure_model_headspace_factor: float = 1.0

    # Bleed rate while dispense solenoid is CLOSED (idle) — MPa/s
    # Measured: 0.35MPa fully bleeds in 5 min → 0.35/300 = 0.00117 MPa/s
    pressure_idle_bleed_mpa_per_s: float = 0.00117

    # Bleed rate while dispense solenoid is OPEN — MPa/s
    # Measured: 0.05 MPa per second of open dispense
    pressure_dispense_bleed_mpa_per_s: float = 0.05

    # Minimum gap between top-up pulses (s).
    # Prevents rapid cycling. Must be > time to charge from low→high (~1.8s).
    # Default 5s: enough for the pressure to stabilise after a pulse.
    pressure_top_up_cooldown_s: float = 2.0

    # Hard ceiling on a single top-up pulse (s).
    # charge_time_s (9s) is the absolute max needed from zero.
    # In maintenance (never from zero), 3–4s is enough for a top-up.
    pressure_top_up_max_s: float = 0.4

    # ── Mid-Run Refill ────────────────────────────────────────────
    mid_refill_threshold_kg: float = 1.2
    mid_refill_target_kg: float = 3.2
    mid_refill_min_gain_kg: float = 0.2
    mid_refill_settle_s: float = 3.0
    mid_refill_cooldown_s: float = 20.0
    mid_refill_max_failures: int = 2


# ── Built-in Profiles ─────────────────────────────────────────────────────────

DEFAULT_PROFILE = PaintProfile(
    name="default",
    description="Open pipe end — measured bleed rates",
    line_prime_mode="open_pipe",
    line_prime_line_volume_kg=0.25,
    line_prime_min_time_s=5.0,
    line_prime_timeout_s=60.0,
    line_prime_max_drain_kg=2.5,
    pressurise_open_s=9.0,
    pressure_low_mpa=0.28,
    pressure_high_mpa=0.35,
    pressure_charge_time_s=25.0,
    pressure_model_ref_kg=3.5,
    pressure_model_headspace_factor=1.0,
    pressure_idle_bleed_mpa_per_s=0.00117,
    pressure_dispense_bleed_mpa_per_s=0.05,
    pressure_top_up_cooldown_s=2.0,
    pressure_top_up_max_s=0.4,
)

THICK_PASTE_PROFILE = PaintProfile(
    name="thick_paste",
    description="High viscosity paste",
    line_prime_mode="open_pipe",
    line_prime_line_volume_kg=0.25,
    line_prime_min_time_s=10.0,
    line_prime_timeout_s=120.0,
    line_prime_max_drain_kg=0.5,
    pot_fill_target_kg=3.0,
    pot_fill_total_timeout_s=120.0,
    pressurise_open_s=9.0,
    dispense_open_ms=600,
    nozzle_open_lag_ms=500,
    nozzle_close_lag_ms=300,
    mid_refill_threshold_kg=1.5,
    mid_refill_target_kg=3.0,
    pressure_low_mpa=0.28,
    pressure_high_mpa=0.35,
    pressure_charge_time_s=35.0,
    pressure_model_ref_kg=3.5,
    pressure_model_headspace_factor=1.2,   # thick paste resists compression
    pressure_idle_bleed_mpa_per_s=0.00117,
    pressure_dispense_bleed_mpa_per_s=0.05,
    pressure_top_up_cooldown_s=2.0,
    pressure_top_up_max_s=0.6,
)

MEDIUM_PROFILE = PaintProfile(
    name="medium",
    description="Medium viscosity",
    pot_fill_target_kg=3.5,
    pot_fill_total_timeout_s=90.0,
    pressurise_open_s=9.0,
    line_prime_min_time_s=10.0,
    line_prime_timeout_s=60.0,
    dispense_open_ms=350,
    nozzle_open_lag_ms=250,
    nozzle_close_lag_ms=150,
    mid_refill_threshold_kg=1.0,
    pressure_low_mpa=0.28,
    pressure_high_mpa=0.35,
    pressure_charge_time_s=25.0,
    pressure_model_ref_kg=3.5,
    pressure_idle_bleed_mpa_per_s=0.00117,
    pressure_dispense_bleed_mpa_per_s=0.05,
    pressure_top_up_cooldown_s=2.0,
    pressure_top_up_max_s=0.4,
)

THIN_PROFILE = PaintProfile(
    name="thin",
    description="Low viscosity — fast fill, short prime",
    pot_fill_target_kg=4.0,
    pot_fill_total_timeout_s=60.0,
    pressurise_open_s=9.0,
    line_prime_min_time_s=5.0,
    line_prime_timeout_s=30.0,
    line_prime_max_drain_kg=1.0,
    dispense_open_ms=200,
    nozzle_open_lag_ms=150,
    nozzle_close_lag_ms=100,
    mid_refill_threshold_kg=0.8,
    mid_refill_target_kg=3.5,
    pressure_low_mpa=0.28,
    pressure_high_mpa=0.35,
    pressure_charge_time_s=5.0,
    pressure_model_ref_kg=3.5,
    pressure_idle_bleed_mpa_per_s=0.00117,
    pressure_dispense_bleed_mpa_per_s=0.05,
    pressure_top_up_cooldown_s=2.0,
    pressure_top_up_max_s=0.2,
)

PROFILES = {
    "default":      DEFAULT_PROFILE,
    "thick_paste":  THICK_PASTE_PROFILE,
    "medium":       MEDIUM_PROFILE,
    "thin":         THIN_PROFILE,
}


def get_profile(name: Optional[str] = None) -> PaintProfile:
    if not name:
        return DEFAULT_PROFILE
    profile = PROFILES.get(name)
    if profile is None:
        print(f"[PAINT_PROFILE] Unknown profile '{name}' — using default")
        return DEFAULT_PROFILE
    print(f"[PAINT_PROFILE] Loaded profile: {profile.name} — {profile.description}")
    return profile