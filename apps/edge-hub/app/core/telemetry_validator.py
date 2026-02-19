class TelemetryValidator:

    MAX_POT_KG = 10.0
    MAX_PRESSURE_BAR = 20.0
    MAX_WEIGHT_JUMP_PER_CYCLE = 1.0   # kg (tune to system physics)

    def sanitize(self, raw: dict, last_valid: dict | None) -> dict:
        last_valid = last_valid or {}

        clean = {}

        # ─────────────────────────────────────
        # 1. TIMESTAMP (reject time rollback)
        # ─────────────────────────────────────
        ts = raw.get("ts")

        if ts is None:
            ts = last_valid.get("ts")

        if last_valid.get("ts") and ts and ts < last_valid["ts"]:
            # Reject out-of-order packet
            return last_valid

        clean["ts"] = ts

        # ─────────────────────────────────────
        # 2. POT WEIGHT
        # ─────────────────────────────────────
        pot = raw.get("pot_weight")
        pot_valid = bool(raw.get("pot_weight_valid", 0))

        prev_pot = last_valid.get("pot_weight", 0.0)

        if pot_valid and pot is not None:
            try:
                pot = float(pot)

                # Physical range check
                if 0 <= pot <= self.MAX_POT_KG:

                    # Physics-based jump filter
                    if abs(pot - prev_pot) <= self.MAX_WEIGHT_JUMP_PER_CYCLE:
                        clean["pot_weight"] = pot
                    else:
                        clean["pot_weight"] = prev_pot
                else:
                    clean["pot_weight"] = prev_pot

            except Exception:
                clean["pot_weight"] = prev_pot
        else:
            clean["pot_weight"] = prev_pot

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
        }

        # ─────────────────────────────────────
        # 6. Threshold Config (pass-through safe)
        # ─────────────────────────────────────
        clean["pot_min_kg"] = float(raw.get("pot_min_kg", last_valid.get("pot_min_kg", 0.4)))
        clean["res_min_kg"] = float(raw.get("res_min_kg", last_valid.get("res_min_kg", 2.0)))

        # ─────────────────────────────────────
        # 7. Weight validity flags
        # ─────────────────────────────────────
        clean["pot_weight_valid"] = 1 if raw.get("pot_weight_valid") else 0
        clean["res_weight_valid"] = 1 if raw.get("res_weight_valid") else 0

        return clean
