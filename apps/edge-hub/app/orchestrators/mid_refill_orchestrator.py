# app/orchestrators/mid_refill_orchestrator.py
#
# FILL PHYSICS FOR THICK VISCOUS PAINT:
#
# Paint flows reservoir → pot only when:
#   reservoir_pressure > pot_pressure + viscosity_resistance
#
# Problem: as paint enters pot, displaced air compresses in pot headspace,
# building back-pressure that progressively stalls flow — especially with
# thick paste that moves slowly and gives headspace pressure time to build.
#
# Solution: keep pot_air_out OPEN throughout fill so displaced air vents
# continuously. This holds pot headspace near atmospheric the whole time.
# Reservoir only needs to overcome viscosity resistance (constant),
# not viscosity + growing back-pressure (nonlinear, stalls).
#
# Sequence:
#   1. DEPRESSURISE_POT       — vent pot to atmospheric
#   2. PRESSURISE_RES         — bring reservoir to working fill pressure
#   3. OPEN_INLET             — open paint_inlet (executor ACK-gated)
#   4. OPEN_VENT              — open pot_air_out to vent during fill
#   5. FILLING                — hold both open, watch weight rise
#   6. CLOSE_INLET            — close paint_inlet first (stops flow)
#   7. CLOSE_VENT             — close pot_air_out second
#   8. SETTLING               — wait for weight cell to stabilise
#   9. DEPRESSURISE_RES       — safe the reservoir
#  10. REPRESSURISE_POT       — bring pot back to working dispense pressure
#
# Valve map (from workflow_builder.py DEVICE_MAP):
#   paint_inlet  (2) — paint flow from reservoir to pot
#   pot_air_in   (3) — pressurises pot for dispense
#   pot_air_out  (4) — vents pot pressure / headspace air during fill
#   res_air_in   (5) — pressurises reservoir for fill
#   res_air_out  (6) — vents reservoir pressure

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

        # Cooldown between refills
        self._last_refill_ts = 0.0

        # Stall detection during fill
        self._fill_last_weight = 0.0
        self._fill_last_weight_ts = 0.0

    # ──────────────────────────────────────────────
    def reset(self):
        self.state = "IDLE"
        self._last_refill_ts = 0.0
        # consecutive_failed_refills lives on MaterialState — reset there if needed

    # ──────────────────────────────────────────────
    def begin(self, profile: PaintProfile):
        if self.state != "IDLE":
            return

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

        mat = material_state_manager.state
        self.profile = profile
        self.weight_before = mat.current_pot_kg
        self._last_refill_ts = now

        print(
            f"[MID_REFILL] Begin — "
            f"pot={self.weight_before:.3f}kg "
            f"target={profile.mid_refill_target_kg}kg"
        )
        program_state.begin_mid_refill()
        self.state = "DEPRESSURISE_POT"

    # ──────────────────────────────────────────────
    def process(self):
        if self.executor.is_busy():
            return

        mat = material_state_manager.state
        p = self.profile
        now = time.time()

        # ── 1. Vent pot to atmospheric ────────────────────────────
        # Must happen before pressurising reservoir.
        # If pot is at working pressure (1.2 bar) and we open inlet,
        # the pressure differential may be insufficient to start flow
        # against thick paste viscosity.
        if self.state == "DEPRESSURISE_POT":
            print("[MID_REFILL] Venting pot to atmospheric")
            self.executor.send_command({
                "name": "pot.depressurise",
                "payload": {}
            })
            self.state = "PRESSURISE_RES"
            return

        # ── 2. Bring reservoir to working fill pressure ───────────
        # Moderate pressure — enough to push thick paste through inlet
        # pipe, not so much it blasts the reservoir seal.
        # pressurise_open_s * 5000ms because reservoir has larger volume
        # than pot and needs longer to reach working pressure.
        # Tune pressurise_open_s in PaintProfile per paint viscosity.
        if self.state == "PRESSURISE_RES":
            print("[MID_REFILL] Pressurising reservoir for fill")
            self.executor.send_command({
                "name": "res.pressurise",
                "payload": {"open_ms": int(p.pressurise_open_s * 5000)}
            })
            self.state = "OPEN_INLET"
            return

        # ── 3. Open inlet ─────────────────────────────────────────
        # Opens paint_inlet valve. Executor ACK-gates so we know
        # firmware confirmed it before proceeding to open vent.
        if self.state == "OPEN_INLET":
            print("[MID_REFILL] Opening paint inlet")
            self.executor.send_command({
                "name": "pot.fill_start",
                "payload": {"target_kg": p.mid_refill_target_kg}
            })
            self.state = "OPEN_VENT"
            return

        # ── 4. Open pot vent ──────────────────────────────────────
        # THIS IS THE KEY STEP FOR THICK VISCOUS PAINT.
        #
        # pot_air_out stays OPEN throughout fill so displaced pot
        # headspace air escapes continuously. Without this:
        #   - Each kg of paint entering compresses ~0.22L of headspace
        #   - Headspace pressure rises ~0.05 bar per kg of paint added
        #   - After 2kg added, pot back-pressure ≈ 0.1 bar
        #   - This reduces effective differential by ~10-15%
        #   - Thick paste flow rate drops nonlinearly → stalls completely
        #
        # With vent open throughout:
        #   - Pot headspace stays at ~0 bar (atmospheric)
        #   - Reservoir pressure only fights viscosity resistance (constant)
        #   - Fill rate stays consistent from start to finish
        #   - No stalling mid-fill
        if self.state == "OPEN_VENT":
            print("[MID_REFILL] Opening pot vent (holds open during fill)")
            self.executor.send_command({
                "name": "pot.vent_open",
                "payload": {}
            })
            # Start fill monitoring
            self.fill_start_ts = now
            self._fill_last_weight = mat.current_pot_kg
            self._fill_last_weight_ts = now
            self.state = "FILLING"
            return

        # ── 5. Monitor fill ───────────────────────────────────────
        # Both paint_inlet and pot_air_out are open.
        # Executor is NOT busy (vent_open ACK received).
        # We just watch weight — no command to send while filling.
        #
        # Three exit conditions:
        #   a) Target weight reached — normal
        #   b) Weight stalled >10s — reservoir empty or pipe blocked
        #   c) Hard timeout — safety ceiling
        if self.state == "FILLING":
            current_kg = mat.current_pot_kg
            elapsed = now - self.fill_start_ts
            gained = current_kg - self.weight_before

            # Update stall detector
            if abs(current_kg - self._fill_last_weight) > 0.01:
                self._fill_last_weight = current_kg
                self._fill_last_weight_ts = now

            time_since_change = now - self._fill_last_weight_ts

            print(
                f"[MID_REFILL] Filling — "
                f"pot={current_kg:.3f}kg "
                f"(+{gained:.3f}kg in {elapsed:.0f}s)"
            )

            # a) Target reached
            if current_kg >= p.mid_refill_target_kg:
                print(f"[MID_REFILL] Target reached ({current_kg:.3f}kg)")
                self.state = "CLOSE_INLET"
                return

            # b) Stall — no weight change for 10s after 5s warmup
            if elapsed > 5.0 and time_since_change > 10.0:
                print(
                    f"[MID_REFILL] Fill stalled — "
                    f"no change for {time_since_change:.0f}s "
                    f"(gained {gained:.3f}kg)"
                )
                self.state = "CLOSE_INLET"
                return

            # c) Hard timeout
            if elapsed > p.pot_fill_total_timeout_s:
                print(f"[MID_REFILL] Fill timeout after {elapsed:.0f}s")
                self.state = "CLOSE_INLET"
                return

            # Still filling — wait for next telemetry tick
            return

        # ── 6. Close inlet first ──────────────────────────────────
        # CLOSE ORDER MATTERS:
        # Close inlet BEFORE vent.
        #
        # If you close vent first while inlet is open:
        #   reservoir pressure has nowhere to go → forces a final
        #   pressure slug of thick paint into sealed pot → spike.
        #
        # Close inlet first → reservoir pressure immediately drops
        # (no more flow path) → safe to close vent with no spike.
        if self.state == "CLOSE_INLET":
            print("[MID_REFILL] Closing inlet first")
            self.executor.send_command({
                "name": "pot.fill_stop",
                "payload": {}
            })
            self.state = "CLOSE_VENT"
            return

        # ── 7. Close pot vent ─────────────────────────────────────
        # Inlet is now confirmed closed (ACK received).
        # Safe to close pot_air_out.
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
        # Weight cell needs time to stabilise after rapid fill.
        # Thick paint sloshes; cell reads falsely high immediately
        # after valve close. Wait settle time before recording gain.
        if self.state == "SETTLING":
            if now - self.settle_start < p.mid_refill_settle_s:
                return

            current_kg = mat.current_pot_kg or 0.0
            gain = current_kg - self.weight_before
            print(f"[MID_REFILL] Settled — gain={gain:.3f}kg")

            # Write outcome directly to MaterialState.
            # rule_engine reads mat.consecutive_failed_refills without
            # needing to import program_engine — no circular dependency.
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

            self.state = "DEPRESSURISE_RES"
            return

        # ── 9. Safe the reservoir ─────────────────────────────────
        # Vent remaining reservoir pressure.
        # Never leave reservoir pressurised at idle — safety risk
        # and causes false pressure readings on next fill.
        if self.state == "DEPRESSURISE_RES":
            print("[MID_REFILL] Venting reservoir")
            self.executor.send_command({
                "name": "res.depressurise",
                "payload": {}
            })
            self.state = "REPRESSURISE_POT"
            return

        # ── 10. Re-pressurise pot for dispense ────────────────────
        # Pot is now at atmospheric (vented during fill, vent now closed).
        # Must return to working pressure before dispense resumes.
        # Uses same pressurise_open_s as startup — same physical result.
        if self.state == "REPRESSURISE_POT":
            print("[MID_REFILL] Re-pressurising pot for dispense")
            self.executor.send_command({
                "name": "pot.pressurise",
                "payload": {"open_ms": int(p.pressurise_open_s * 1000)}
            })
            self.state = "COMPLETE"
            return

        # ── 11. Done ─────────────────────────────────────────────
        if self.state == "COMPLETE":
            print("[MID_REFILL] Complete → RUNNING")
            self.state = "IDLE"
            program_state.on_mid_refill_done()

# import time
# from app.services.command_executor import CommandExecutor
# from app.state.material_state import material_state_manager
# from app.state.program_state import program_state
# from app.config.paint_profile import PaintProfile


# class MidRefillOrchestrator:

#     def __init__(self, executor: CommandExecutor):
#         self.executor = executor
#         self.profile: PaintProfile = None
#         self.state = "IDLE"

#         self.weight_before = 0.0
#         self.settle_start = 0.0

#     # ──────────────────────────────────────────────
#     def reset(self):
#         self.state = "IDLE"

#     # ──────────────────────────────────────────────
#     def begin(self, profile: PaintProfile):
#         if self.state != "IDLE":
#             return

#         mat = material_state_manager.state
#         self.profile = profile
#         self.weight_before = mat.current_pot_kg

#         print("[MID_REFILL] Pressure-assisted refill begin")
#         program_state.begin_mid_refill()

#         self.state = "DEPRESSURISE_POT"

#     # ──────────────────────────────────────────────
#     def process(self):

#         if self.executor.is_busy():
#             return

#         mat = material_state_manager.state
#         p = self.profile

#         # 1️⃣ Depressurise pot
#         if self.state == "DEPRESSURISE_POT":
#             print("[MID_REFILL] Depressurising pot")
#             self.executor.send_command({"name": "pot.depressurise", "payload": {}})
#             self.state = "PRESSURISE_RES"
#             return

#         # 2️⃣ Pressurise reservoir
#         if self.state == "PRESSURISE_RES":
#             print("[MID_REFILL] Pressurising reservoir")
#             self.executor.send_command({
#                 "name": "res.pressurise",
#                 "payload": {"open_ms": int(p.pressurise_open_s * 5000)}
#             })
#             self.state = "OPEN_INLET"
#             return

#         # 3️⃣ Open inlet
#         if self.state == "OPEN_INLET":
#             print("[MID_REFILL] Opening paint inlet")
#             self.executor.send_command({
#                 "name": "pot.fill_start",
#                 "payload": {"target_kg": p.mid_refill_target_kg}
#             })
#             self.state = "WAIT_TARGET"
#             return

#         # 4️⃣ Wait for target
#         if self.state == "WAIT_TARGET":
#             # if mat.current_pot_kg >= p.mid_refill_target_kg:
#             print("[MID_REFILL] Target reached")
#             self.executor.send_command({
#                 "name": "pot.fill_stop",
#                 "payload": {}
#             })
#             self.settle_start = time.time()
#             self.state = "SETTLING"
#             return

#         # 5️⃣ Settling
#         if self.state == "SETTLING":
#             if time.time() - self.settle_start < p.mid_refill_settle_s:
#                 return

#             gain = mat.current_pot_kg - self.weight_before
#             print(f"[MID_REFILL] Gain after settle: {gain:.3f}kg")

#             self.state = "DEPRESSURISE_RES"
#             return

#         # 6️⃣ Depressurise reservoir
#         if self.state == "DEPRESSURISE_RES":
#             print("[MID_REFILL] Depressurising reservoir")
#             self.executor.send_command({"name": "res.depressurise", "payload": {}})
#             self.state = "REPRESSURISE_POT"
#             return

#         # 7️⃣ Re-pressurise pot
#         if self.state == "REPRESSURISE_POT":
#             print("[MID_REFILL] Re-pressurising pot")
#             self.executor.send_command({
#                 "name": "pot.pressurise",
#                 "payload": {"open_ms": int(p.pressurise_open_s * 1000)}
#             })
#             self.state = "COMPLETE"
#             return

#         # 8️⃣ Complete
#         if self.state == "COMPLETE":
#             print("[MID_REFILL] Refill complete → RUNNING")
#             self.state = "IDLE"
#             program_state.on_mid_refill_done()
