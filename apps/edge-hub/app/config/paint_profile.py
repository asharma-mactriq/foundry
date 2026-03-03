# app/config/paint_profile.py
#
# All timing parameters that vary per paint type live here.
# Each program config from NestJS should include a "paint_profile" key.
# If absent, DEFAULT_PROFILE is used.
#
# HOW TO TUNE:
#   1. Run with DEFAULT_PROFILE first
#   2. Watch logs — each phase logs actual measured values
#   3. Copy DEFAULT_PROFILE, adjust numbers, save as new profile
#   4. Pass profile name in program config: {"paint_profile": "thick_fabric"}

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class PaintProfile:
    # ── Identity ──────────────────────────────────────────────────
    name: str = "default"
    description: str = ""

    # ── Pot Fill ──────────────────────────────────────────────────
    # How full to fill the pot before pressurising (kg)
    # Thick paste: fill less (harder to push) — start at 3.0
    # Thin paint:  fill more (flows easy)      — go up to 4.5
    pot_fill_target_kg: float = 3.5

    # How long to wait after inlet opens before expecting weight gain
    # Thick paste needs longer to start moving through the 1" pipe
    pot_fill_flow_start_timeout_s: float = 8.0   # abort if no gain after this

    # Total fill timeout (weight moving but slowly)
    pot_fill_total_timeout_s: float = 90.0

    # Minimum weight gain to confirm flow has started
    pot_fill_min_gain_kg: float = 0.05

    # Settle time after closing inlet before pressurising
    # Weight cell needs to stabilise — thick paste sloshes less, but give it time
    pot_fill_settle_s: float = 2.0
    pot_fill_open_time_s: float = 6.0
    # ── Pressurisation ────────────────────────────────────────────
    # Fixed open time for pot_air_in (time-based, not pressure-based)
    # 6L pot at 3 bar input — 10-15s is typical
    # Thick paste needs higher pressure to flow → err on longer side
    pressurise_open_s: float = 4.0

    # Hard ceiling — never exceed this open time regardless of anything
    pressurise_max_open_s: float = 25.0

    # Safety: if pressure sensor reads above this → close immediately (overpressure)
    # Set conservatively — fire extinguisher body rated >> 3 bar but be safe
    pressurise_safety_bar: float = 2.8

    # If sensor reads above this AND min time passed → close early (opportunistic)
    # Only used if pressure sensor is trusted
    pressurise_confirm_bar: float = 0.6

    # ── Line Priming ──────────────────────────────────────────────
    # 5ft × 1/2" pipe + 5 spring nozzles
    # Thick paste: line fills slowly, nozzle crack pressure is significant

    # Minimum time before even checking for prime completion
    # Thick paste in 5ft line: 30-60s minimum
    line_prime_min_time_s: float = 1.0

    # Hard timeout — abort if not primed by this time
    line_prime_timeout_s: float = 2.0

    # Safety: close and abort if this much paint drained without prime detection
    # 5ft × 1/2" pipe volume ≈ 0.5L ≈ 0.5-0.8kg for thick paste
    # Allow 2x for safety margin
    line_prime_max_drain_kg: float = 1.2

    # Drop rate (kg/s) that indicates nozzles have cracked open
    # Thick paste: lower rate due to viscosity — tune from logs
    # Start conservative, reduce if prime detection is too late
    line_prime_nozzle_crack_rate_kg_s: float = 1.0   # 1kg/s

    # After nozzle crack detected, confirm stable flow for this long before declaring primed
    line_prime_stable_confirm_s: float = 0.5

    # Rate sampling window for line prime detection
    line_prime_rate_window_s: float = 0.05

    # Prime detection strategy:
    #   "open_pipe"     — open end, no nozzle. Prime detected by drain volume.
    #   "spring_nozzle" — nozzles at end. Prime detected by crack rate spike.
    line_prime_mode: str = "open_pipe"

    # Volume of paint needed to fill the line from pot to end (kg).
    # Used only in open_pipe mode.
    # Calculate: pipe_volume_litres × paint_density_kg_per_litre
    #
    # Your system: 5ft × 0.5" ID pipe
    #   Volume = π × (0.0064m)² × 1.524m = ~0.000197 m³ = 0.197L
    #   Thick paste density ~1.3 kg/L → 0.197 × 1.3 = ~0.256kg
    #   Set to 0.25 as a safe starting point. Tune down if prime detects late.
    line_prime_line_volume_kg: float = 0.25

    # ── Dispense ──────────────────────────────────────────────────
    # Solenoid open duration per gap (ms)
    # This is the SOLENOID open time, not the actual paint-out time
    # Tune this first before worrying about lags
    dispense_open_ms: int = 400

    # Lag from solenoid open to paint actually exiting nozzles (ms)
    # Accounts for: pressure wave travel, nozzle spring overcome, viscosity
    # Thick paste: 300-800ms — measure empirically
    # Watch pot weight: starts dropping = nozzles cracked open
    nozzle_open_lag_ms: int = 300

    # Lag from solenoid close to paint stopping at nozzle (ms)
    # Residual pressure in 5ft line keeps pushing briefly
    # Thick paste: 100-400ms
    nozzle_close_lag_ms: int = 200

    # Effective dispense time = open_ms - open_lag - close_lag
    # If this goes negative your open_ms is too short for this paint
    @property
    def effective_dispense_ms(self) -> int:
        return max(0, self.dispense_open_ms - self.nozzle_open_lag_ms - self.nozzle_close_lag_ms)

    # Between-plate maintenance: brief solenoid pulse to keep line pressurised
    # Prevents thick paste from settling/blocking in 5ft line between plates
    # Set to 0 to disable
    inter_plate_maintain_open_ms: int = 0   # disabled until tested

    # ── Mid-Run Refill ────────────────────────────────────────────
    # Trigger refill when pot drops below this (kg)
    # Thick paste: trigger higher — harder to refill quickly
    mid_refill_threshold_kg: float = 1.2

    # Refill target (kg) — don't overfill, leave headspace for air
    mid_refill_target_kg: float = 3.2

    # Minimum weight gain to consider refill successful
    mid_refill_min_gain_kg: float = 0.2

    # Settle time after closing inlet during mid-run refill
    mid_refill_settle_s: float = 3.0

    # Cooldown between refill attempts (s)
    mid_refill_cooldown_s: float = 20.0

    # Max consecutive failed refills before locking out
    mid_refill_max_failures: int = 2


# ── Built-in Profiles ─────────────────────────────────────────────────────────

# # Use this until you have real measurements
# DEFAULT_PROFILE = PaintProfile(
#     name="default",
#     description="Conservative defaults for unknown paint — tune from here"
# )

DEFAULT_PROFILE = PaintProfile(
    name="default",
    description="Conservative defaults — open pipe end",
    line_prime_mode="open_pipe",
    line_prime_line_volume_kg=0.25,
    line_prime_min_time_s=5.0,       # give pressure time to stabilise
    line_prime_timeout_s=60.0,       # abort if 0.25kg not drained in 60s
    line_prime_max_drain_kg=1.0,     # safety cap: never drain more than 500g
)

# Thick paste (fabric paint, Fevicol-like consistency)
THICK_PASTE_PROFILE = PaintProfile(
    name="thick_paste",
    description="High viscosity paste — open pipe, slow fill",
    line_prime_mode="open_pipe",
    line_prime_line_volume_kg=0.25,
    line_prime_min_time_s=10.0,      # thick paste moves slowly
    line_prime_timeout_s=120.0,
    line_prime_max_drain_kg=0.5,
    line_prime_nozzle_crack_rate_kg_s=0.003,
    pot_fill_target_kg=3.0,
    pot_fill_flow_start_timeout_s=12.0,
    pressurise_open_s=15.0,
    pot_fill_total_timeout_s=120.0,
    dispense_open_ms=600,
    nozzle_open_lag_ms=500,
    nozzle_close_lag_ms=300,
    mid_refill_threshold_kg=1.5,
    mid_refill_target_kg=3.0,
)

# Medium viscosity (standard fabric paint, flowing but not watery)
MEDIUM_PROFILE = PaintProfile(
    name="medium",
    description="Medium viscosity — moderate timings",
    pot_fill_target_kg=3.5,
    pot_fill_flow_start_timeout_s=8.0,
    pressurise_open_s=12.0,
    line_prime_min_time_s=25.0,
    line_prime_timeout_s=150.0,
    dispense_open_ms=350,
    nozzle_open_lag_ms=250,
    nozzle_close_lag_ms=150,
    mid_refill_threshold_kg=1.0,
)

# Thin paint (water-like consistency)
THIN_PROFILE = PaintProfile(
    name="thin",
    description="Low viscosity — fast fill, short prime, small lags",
    pot_fill_target_kg=4.0,
    pot_fill_flow_start_timeout_s=5.0,
    pot_fill_total_timeout_s=60.0,
    pressurise_open_s=10.0,
    line_prime_min_time_s=15.0,
    line_prime_timeout_s=90.0,
    line_prime_max_drain_kg=1.0,
    line_prime_nozzle_crack_rate_kg_s=0.010,
    dispense_open_ms=200,
    nozzle_open_lag_ms=150,
    nozzle_close_lag_ms=100,
    mid_refill_threshold_kg=0.8,
    mid_refill_target_kg=3.5,
)

PROFILES = {
    "default":      DEFAULT_PROFILE,
    "thick_paste":  THICK_PASTE_PROFILE,
    "medium":       MEDIUM_PROFILE,
    "thin":         THIN_PROFILE,
}


def get_profile(name: Optional[str] = None) -> PaintProfile:
    """
    Return profile by name. Falls back to DEFAULT if name unknown.
    Logs warning so operator knows a fallback happened.
    """
    if not name:
        return DEFAULT_PROFILE
    profile = PROFILES.get(name)
    if profile is None:
        print(f"[PAINT_PROFILE] Unknown profile '{name}' — using default")
        return DEFAULT_PROFILE
    print(f"[PAINT_PROFILE] Loaded profile: {profile.name} — {profile.description}")
    return profile