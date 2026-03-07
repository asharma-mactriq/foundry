# app/core/telemetry_validator.py

from typing import Optional


class TelemetryValidator:
    """
    Industrial-grade telemetry validator.

    Features:
    - Accepts first valid reading as baseline (tare model)
    - Tracks relative pot mass change
    - Preserves absolute mass for safety checks
    - Applies physics-based jump filtering AFTER baseline exists
    - Never silently fabricates 0kg on startup
    """

    MAX_POT_KG = 50.0                 # Set above physical maximum
    MAX_PRESSURE_BAR = 20.0
    MAX_WEIGHT_JUMP_PER_CYCLE = 6.0   # kg per telemetry cycle (tune to system)

    def __init__(self):
        self.baseline_pot: Optional[float] = None

    # ---------------------------------------------------------
    # External reset hook (call after refill / program start)
    # ---------------------------------------------------------
    def reset_baseline(self):
        self.baseline_pot = None

    # ---------------------------------------------------------
    # Main sanitize pipeline
    # ---------------------------------------------------------
    def sanitize(self, raw: dict, last_valid: dict | None) -> dict:
        last_valid = last_valid or {}
        clean = {}

        # ─────────────────────────────────────
        # 1. TIMESTAMP (reject rollback)
        # ─────────────────────────────────────
        ts = raw.get("ts")

        if ts is None:
            ts = last_valid.get("ts")

        if last_valid.get("ts") and ts and ts < last_valid["ts"]:
            return last_valid

        clean["ts"] = ts

        # ─────────────────────────────────────
        # 2. POT WEIGHT (absolute + relative model)
        # ─────────────────────────────────────
        pot_raw = raw.get("pot_weight")
        pot_valid = bool(raw.get("pot_weight_valid", 0))

        prev_relative = last_valid.get("pot_weight", 0.0)
        prev_absolute = last_valid.get("pot_weight_absolute")

        absolute_weight = prev_absolute
        relative_weight = prev_relative

        if pot_valid and pot_raw is not None:
            try:
                pot = float(pot_raw)

                # Physical range check
                if 0 <= pot <= self.MAX_POT_KG:

                    # Accept first valid packet as baseline
                    if self.baseline_pot is None:
                        self.baseline_pot = pot
                        absolute_weight = pot
                        relative_weight = 0.0

                    else:
                        # Jump filtering only after baseline established
                        if prev_absolute is not None:
                            if abs(pot - prev_absolute) > self.MAX_WEIGHT_JUMP_PER_CYCLE:
                                pot = prev_absolute  # reject unrealistic jump

                        absolute_weight = pot
                        delta = pot - self.baseline_pot

                        # Relative mass cannot go negative
                        relative_weight = max(delta, 0.0)

            except Exception:
                pass  # fall back to previous

        clean["pot_weight_absolute"] = absolute_weight
        clean["pot_weight"] = relative_weight

        # ─────────────────────────────────────
        # 3. PRESSURE
        # ─────────────────────────────────────
        prev_pressure = last_valid.get("pot_pressure", 0.0)

        try:
            pressure = float(raw.get("pot_pressure", prev_pressure))

            if -1 <= pressure <= self.MAX_PRESSURE_BAR:
                clean["pot_pressure"] = pressure
            else:
                clean["pot_pressure"] = prev_pressure

        except Exception:
            clean["pot_pressure"] = prev_pressure

        # ─────────────────────────────────────
        # 4. GAP (force boolean)
        # ─────────────────────────────────────
        clean["gap"] = 1 if raw.get("gap") else 0

        # ─────────────────────────────────────
        # 5. VALVES (strict schema)
        # ─────────────────────────────────────
        raw_valves = raw.get("valves", {})

        clean["valves"] = {
            "dispense": 1 if raw_valves.get("dispense") else 0,
            "paint_inlet": 1 if raw_valves.get("paint_inlet") else 0,
            "pot_air_in": 1 if raw_valves.get("pot_air_in") else 0,
            "pot_air_out": 1 if raw_valves.get("pot_air_out") else 0,
            "res_air_in": 1 if raw_valves.get("res_air_in") else 0,
            "res_air_out": 1 if raw_valves.get("res_air_out") else 0,
            "nozzle": 1 if raw_valves.get("nozzle") else 0,
        }

        # ─────────────────────────────────────
        # 6. Threshold Config
        # ─────────────────────────────────────
        clean["pot_min_kg"] = float(
            raw.get("pot_min_kg", last_valid.get("pot_min_kg", 0.4))
        )
        clean["res_min_kg"] = float(
            raw.get("res_min_kg", last_valid.get("res_min_kg", 2.0))
        )

        # ─────────────────────────────────────
        # 7. Validity Flags
        # ─────────────────────────────────────
        clean["pot_weight_valid"] = 1 if raw.get("pot_weight_valid") else 0
        clean["res_weight_valid"] = 1 if raw.get("res_weight_valid") else 0

        return clean

# class TelemetryValidator:

#     MAX_POT_KG = 10.0
#     MAX_PRESSURE_BAR = 20.0
#     MAX_WEIGHT_JUMP_PER_CYCLE = 6.0   # kg (tune to system physics)

#     def sanitize(self, raw: dict, last_valid: dict | None) -> dict:
#         last_valid = last_valid or {}

#         clean = {}

#         # ─────────────────────────────────────
#         # 1. TIMESTAMP (reject time rollback)
#         # ─────────────────────────────────────
#         ts = raw.get("ts")

#         if ts is None:
#             ts = last_valid.get("ts")

#         if last_valid.get("ts") and ts and ts < last_valid["ts"]:
#             # Reject out-of-order packet
#             return last_valid

#         clean["ts"] = ts

#         # ─────────────────────────────────────
#         # 2. POT WEIGHT
#         # ─────────────────────────────────────
#         pot = raw.get("pot_weight")
#         pot_valid = bool(raw.get("pot_weight_valid", 0))

#         prev_pot = last_valid.get("pot_weight", 0.0)

#         if pot_valid and pot is not None:
#             try:
#                 pot = float(pot)

#                 # Physical range check
#                 if 0 <= pot <= self.MAX_POT_KG:

#                     # Physics-based jump filter
#                     if abs(pot - prev_pot) <= self.MAX_WEIGHT_JUMP_PER_CYCLE:
#                         clean["pot_weight"] = pot
#                     else:
#                         clean["pot_weight"] = prev_pot
#                 else:
#                     clean["pot_weight"] = prev_pot

#             except Exception:
#                 clean["pot_weight"] = prev_pot
#         else:
#             clean["pot_weight"] = prev_pot

#         # ─────────────────────────────────────
#         # 3. PRESSURE
#         # ─────────────────────────────────────
#         prev_pressure = last_valid.get("pot_pressure", 0.0)

#         try:
#             pressure = float(raw.get("pot_pressure", prev_pressure))

#             if -1 <= pressure <= self.MAX_PRESSURE_BAR:
#                 clean["pot_pressure"] = pressure
#             else:
#                 clean["pot_pressure"] = prev_pressure

#         except Exception:
#             clean["pot_pressure"] = prev_pressure

#         # ─────────────────────────────────────
#         # 4. GAP (force boolean)
#         # ─────────────────────────────────────
#         clean["gap"] = 1 if raw.get("gap") else 0

#         # ─────────────────────────────────────
#         # 5. VALVES (strict schema)
#         # ─────────────────────────────────────
#         raw_valves = raw.get("valves", {})

#         clean["valves"] = {
#             "dispense": 1 if raw_valves.get("dispense") else 0,
#             "paint_inlet": 1 if raw_valves.get("paint_inlet") else 0,
#             "pot_air_in": 1 if raw_valves.get("pot_air_in") else 0,
#             "pot_air_out": 1 if raw_valves.get("pot_air_out") else 0,
#             "res_air_in": 1 if raw_valves.get("res_air_in") else 0,
#             "res_air_out": 1 if raw_valves.get("res_air_out") else 0,
#         }

#         # ─────────────────────────────────────
#         # 6. Threshold Config (pass-through safe)
#         # ─────────────────────────────────────
#         clean["pot_min_kg"] = float(raw.get("pot_min_kg", last_valid.get("pot_min_kg", 0.4)))
#         clean["res_min_kg"] = float(raw.get("res_min_kg", last_valid.get("res_min_kg", 2.0)))

#         # ─────────────────────────────────────
#         # 7. Weight validity flags
#         # ─────────────────────────────────────
#         clean["pot_weight_valid"] = 1 if raw.get("pot_weight_valid") else 0
#         clean["res_weight_valid"] = 1 if raw.get("res_weight_valid") else 0

#         return clean
