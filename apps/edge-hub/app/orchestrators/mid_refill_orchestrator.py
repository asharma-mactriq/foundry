# app/orchestrators/mid_refill_orchestrator.py
#
# Sequence:
#   1. OPEN_VENT          — open pot_air_out, hold min 5s
#   2. PRESSURISE_RES     — bring reservoir to working fill pressure
#   3. OPEN_INLET         — open paint_inlet, watch weight
#   4. FILLING            — wait until 90% of mid_refill_target_kg reached
#   5. CLOSE_INLET        — close paint_inlet first (stops flow)
#   6. CLOSE_RES          — vent reservoir pressure
#   7. CLOSE_VENT         — close pot_air_out
#   8. SETTLING           — wait for weight cell to stabilise
#   9. REPRESSURISE_POT   — open pot_air_in for pressure_charge_time_s
#  10. STOP_POT_PRESSURISE — close pot_air_in, seed pressure model
#  11. COMPLETE           — on_mid_refill_done() → RUNNING

import time
from app.services.command_executor import CommandExecutor
from app.state.material_state import material_state_manager
from app.state.program_state import program_state
from app.config.paint_profile import PaintProfile


class MidRefillOrchestrator:

    def __init__(self, executor: CommandExecutor):
        self.executor = executor
        self.profile: PaintProfile = None
        self.state = "IDLE"

        self.weight_before = 0.0
        self.fill_start_ts = 0.0
        self.settle_start = 0.0

        self._last_refill_ts = 0.0

        self._fill_last_weight = 0.0
        self._fill_last_weight_ts = 0.0

        self._vent_open_ts = 0.0
        self._pot_pressurise_ts = 0.0
        self._vent_cmd_completed = False
        self._pot_pressurise_cmd_completed = False

        # CHANGE 1: track actual open duration for pressure seeding
        self._pot_pressurise_open_s = 0.0

    # ──────────────────────────────────────────────
    def reset(self):
        self.state = "IDLE"
        self._last_refill_ts = 0.0
        self._vent_open_ts = 0.0
        self._pot_pressurise_ts = 0.0
        self._vent_cmd_completed = False
        self._pot_pressurise_cmd_completed = False
        self._pot_pressurise_open_s = 0.0

    # ──────────────────────────────────────────────
    def begin(self, profile: PaintProfile):
        if self.state != "IDLE":
            return

        mat = material_state_manager.state
        now = time.time()

        if now - self._last_refill_ts < profile.mid_refill_cooldown_s:
            remaining = profile.mid_refill_cooldown_s - (now - self._last_refill_ts)
            print(f"[MID_REFILL] Cooldown — {remaining:.0f}s remaining")
            return

        if mat.consecutive_failed_refills >= profile.mid_refill_max_failures:
            print(
                f"[MID_REFILL] Locked out — "
                f"{mat.consecutive_failed_refills} consecutive failures, "
                f"reservoir likely empty"
            )
            return

        self.profile = profile
        self.weight_before = mat.current_pot_kg
        self._last_refill_ts = now
        self._vent_cmd_completed = False
        self._pot_pressurise_cmd_completed = False
        self._pot_pressurise_open_s = 0.0

        print(
            f"[MID_REFILL] Begin — "
            f"pot={self.weight_before:.3f}kg "
            f"target=90% of {profile.mid_refill_target_kg}kg "
            f"= {profile.mid_refill_target_kg * 0.9:.3f}kg"
        )
        program_state.begin_mid_refill()
        self.state = "OPEN_VENT"

    # ──────────────────────────────────────────────
    def process(self):
        if self.executor.is_busy():
            return

        mat = material_state_manager.state
        p = self.profile
        now = time.time()

        fill_target_kg = p.mid_refill_target_kg * 0.9

        # ── 1. Open pot vent — hold min 5s ───────────────────────
        if self.state == "OPEN_VENT":
            if not self._vent_cmd_completed:
                print("[MID_REFILL] Opening pot vent (min 5s)")
                self.executor.send_command({
                    "name": "pot.vent_open",
                    "payload": {}
                })
                self._vent_open_ts = now
                self._vent_cmd_completed = True
                return

            vent_elapsed = now - self._vent_open_ts
            if vent_elapsed >= 5.0:
                print(f"[MID_REFILL] Pot vent open for {vent_elapsed:.1f}s → pressurising reservoir")
                self.state = "PRESSURISE_RES"
            return

        # ── 2. Pressurise reservoir ───────────────────────────────
        if self.state == "PRESSURISE_RES":
            print("[MID_REFILL] Pressurising reservoir for fill")
            self.executor.send_command({
                "name": "res.pressurise",
                "payload": {"open_ms": int(p.pressurise_open_s * 1000)}
            })
            self.state = "OPEN_INLET"
            return

        # ── 3. Open inlet ─────────────────────────────────────────
        if self.state == "OPEN_INLET":
            print(
                f"[MID_REFILL] Opening paint inlet "
                f"(filling to 90% = {fill_target_kg:.3f}kg)"
            )
            self.executor.send_command({
                "name": "pot.fill_start",
                "payload": {"target_kg": fill_target_kg}
            })
            self.fill_start_ts = now
            self._fill_last_weight = mat.current_pot_kg
            self._fill_last_weight_ts = now
            self.state = "FILLING"
            return

        # ── 4. Monitor fill ───────────────────────────────────────
        if self.state == "FILLING":
            current_kg = mat.current_pot_kg
            elapsed = now - self.fill_start_ts
            gained = current_kg - self.weight_before

            if abs(current_kg - self._fill_last_weight) > 0.01:
                self._fill_last_weight = current_kg
                self._fill_last_weight_ts = now

            time_since_change = now - self._fill_last_weight_ts

            print(
                f"[MID_REFILL] Filling — "
                f"pot={current_kg:.3f}kg / {fill_target_kg:.3f}kg "
                f"(+{gained:.3f}kg in {elapsed:.0f}s)"
            )

            if current_kg >= fill_target_kg:
                print(f"[MID_REFILL] 90% target reached ({current_kg:.3f}kg)")
                self.state = "CLOSE_INLET"
                return

            if elapsed > 5.0 and time_since_change > 10.0:
                print(
                    f"[MID_REFILL] Fill stalled — "
                    f"no change for {time_since_change:.0f}s "
                    f"(gained {gained:.3f}kg)"
                )
                self.state = "CLOSE_INLET"
                return

            if elapsed > p.pot_fill_total_timeout_s:
                print(f"[MID_REFILL] Fill timeout after {elapsed:.0f}s")
                self.state = "CLOSE_INLET"
                return

            return

        # ── 5. Close inlet ────────────────────────────────────────
        if self.state == "CLOSE_INLET":
            print("[MID_REFILL] Closing paint inlet")
            self.executor.send_command({
                "name": "pot.fill_stop",
                "payload": {}
            })
            self.state = "CLOSE_RES"
            return

        # ── 6. Vent reservoir ─────────────────────────────────────
        if self.state == "CLOSE_RES":
            print("[MID_REFILL] Venting reservoir")
            self.executor.send_command({
                "name": "res.depressurise",
                "payload": {}
            })
            self.state = "CLOSE_VENT"
            return

        # ── 7. Close pot vent ─────────────────────────────────────
        if self.state == "CLOSE_VENT":
            print("[MID_REFILL] Closing pot vent")
            self.executor.send_command({
                "name": "pot.vent_close",
                "payload": {}
            })
            self.settle_start = now
            self.state = "SETTLING"
            return

        # ── 8. Settle ─────────────────────────────────────────────
        if self.state == "SETTLING":
            if now - self.settle_start < p.mid_refill_settle_s:
                return

            current_kg = mat.current_pot_kg or 0.0
            gain = current_kg - self.weight_before
            print(f"[MID_REFILL] Settled — gain={gain:.3f}kg")

            mat.last_refill_gain_kg = gain
            mat.last_refill_weight_before = self.weight_before

            if gain < p.mid_refill_min_gain_kg:
                mat.consecutive_failed_refills += 1
                print(
                    f"[MID_REFILL] Low gain — failure "
                    f"{mat.consecutive_failed_refills}/{p.mid_refill_max_failures}"
                )
            else:
                mat.consecutive_failed_refills = 0
                print("[MID_REFILL] Refill successful")

            self._pot_pressurise_cmd_completed = False
            self.state = "REPRESSURISE_POT"
            return

        # ── 9. Re-pressurise pot ──────────────────────────────────
        # CHANGE 2: hold for pressure_charge_time_s (from profile)
        # instead of hardcoded 5s. This is the physically measured time
        # to reach pressure_high_mpa at full pot. Using it here ensures
        # the pot is reliably at the top of the working range before
        # RUNNING resumes, matching startup behaviour exactly.
        if self.state == "REPRESSURISE_POT":
            if not self._pot_pressurise_cmd_completed:
                print(
                    f"[MID_REFILL] Re-pressurising pot "
                    f"(target={p.pressure_charge_time_s}s)"
                )
                self.executor.send_command({
                    "name": "pot.pressurise",
                    "payload": {}
                })
                self._pot_pressurise_ts = now
                self._pot_pressurise_cmd_completed = True
                return

            pot_elapsed = now - self._pot_pressurise_ts
            # CHANGE 2 (continued): use pressure_charge_time_s not 5.0
            if pot_elapsed >= p.pressure_charge_time_s:
                print(
                    f"[MID_REFILL] Pot pressurised for "
                    f"{pot_elapsed:.1f}s → closing pot_air_in"
                )
                # CHANGE 1: record actual duration for seeding
                self._pot_pressurise_open_s = pot_elapsed
                self.state = "STOP_POT_PRESSURISE"
            return

        # ── 10. Close pot_air_in ──────────────────────────────────
        if self.state == "STOP_POT_PRESSURISE":
            print("[MID_REFILL] Closing pot_air_in")
            self.executor.send_command({
                "name": "pot.pressurise_stop",
                "payload": {}
            })
            self.state = "COMPLETE"
            return

        # ── 11. Done ──────────────────────────────────────────────
        if self.state == "COMPLETE":
            print("[MID_REFILL] Complete → RUNNING")
            self.state = "IDLE"

            # CHANGE 3: seed program_engine pressure model before
            # handing control back to RUNNING. Without this, the model
            # still has whatever decayed value it had when refill started
            # (likely near zero after the vent-open fill sequence).
            # With this, it knows the pot is back at pressure_high_mpa
            # and won't fire an immediate top-up pulse on the next tick.
            mat = material_state_manager.state
            current_kg = mat.current_pot_kg or self.profile.pressure_model_ref_kg
            self._seed_program_engine_pressure(
                open_s=self._pot_pressurise_open_s,
                current_kg=current_kg
            )

            program_state.on_mid_refill_done()

    def _seed_program_engine_pressure(self, open_s: float, current_kg: float):
        """
        Notify program_engine of how much pot_air_in time was banked
        during REPRESSURISE_POT so it starts with an accurate estimate.
        """
        try:
            from app.program.program_engine import program_engine
            if program_engine is not None:
                program_engine.seed_pressure(open_s=open_s, current_kg=current_kg)
        except Exception as e:
            print(f"[MID_REFILL] Could not seed pressure model: {e}")