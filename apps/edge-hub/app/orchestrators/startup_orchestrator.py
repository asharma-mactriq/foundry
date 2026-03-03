# # app/orchestrators/startup_orchestrator.py

# import time
# from app.state.program_state import program_state, ProgramPhase
# from app.state.material_state import material_state_manager
# from app.state.machine_state import machine_state_manager
# from app.config.paint_profile import PaintProfile, DEFAULT_PROFILE


# class StartupOrchestrator:
#     """
#     Drives the startup sequence:
#         STARTUP → POT_FILLING → PRESSURISING → LINE_PRIMING → READY

#     POT FILLING — full pressure-assisted sequence (same physics as mid_refill):
#         1. Vent pot to atmospheric       (pot_air_out open briefly)
#         2. Pressurise reservoir          (res_air_in open for pressurise_open_s * 5s)
#         3. Open paint inlet              (paint_inlet open)
#         4. Open pot vent continuously    (pot_air_out held open during fill)
#         5. Monitor weight to target
#         6. Close inlet first             (stops paint flow)
#         7. Close vent second             (safe — no pressure behind it)
#         8. Depressurise reservoir        (safe the reservoir)
#         9. Settle weight cell
#         → PRESSURISING (pot_air_in opens to bring pot to working pressure)

#     Without reservoir pressurisation, thick viscous paint will not move
#     through the inlet pipe. Gravity alone is insufficient.
#     Without continuous pot venting, displaced headspace air builds
#     back-pressure and stalls flow mid-fill.

#     LINE PRIMING — two modes set in PaintProfile.line_prime_mode:
#         "open_pipe"     — open end, prime detected by drain volume
#         "spring_nozzle" — nozzles at end, prime detected by crack rate spike
#     """

#     def __init__(self):
#         self.profile: PaintProfile = DEFAULT_PROFILE
#         self._reset_state()

#     def _reset_state(self):
#         # Fill phase — step flags in sequence order
#         self._fill_depressurised_pot = False
#         self._fill_res_pressurised = False
#         self._fill_inlet_opened = False
#         self._fill_vent_opened = False
#         self._fill_inlet_closed = False
#         self._fill_vent_closed = False
#         self._fill_res_depressurised = False

#         self._fill_phase_start_ts = 0.0
#         self._fill_phase_start_weight = 0.0
#         self._fill_last_weight = 0.0
#         self._fill_last_weight_ts = 0.0
#         self._settle_start_ts = 0.0

#         # Pressurise phase
#         self._pressurise_cmd_sent = False
#         self._pressurise_start_ts = 0.0

#         # Line prime phase
#         self._prime_cmd_sent = False
#         self._prime_stop_sent = False
#         self._prime_start_ts = 0.0
#         self._prime_start_weight = 0.0
#         self._rate_window_start_ts = 0.0
#         self._rate_window_start_weight = 0.0
#         self._peak_drop_rate = 0.0
#         self._nozzle_crack_ts = 0.0
#         self._nozzle_cracked = False

#     def reset(self):
#         self._reset_state()
#         print("[STARTUP_ORCH] Reset")

#     def begin(self, profile: PaintProfile = None):
#         """
#         Called once when startup.sequence ACK completes.
#         Transitions STARTUP → POT_FILLING.
#         """
#         if profile:
#             self.profile = profile

#         mat = material_state_manager.state
#         now = time.time()

#         current_kg = mat.current_pot_kg or 0.0
#         target_kg = self.profile.pot_fill_target_kg

#         # ── Skip fill if pot already at or above target ────────────
#         # Inlet is already closed — do not send pot.fill_stop.
#         # Just pass through POT_FILLING → PRESSURISING directly.
#         if current_kg >= target_kg:
#             print(
#                 f"[STARTUP_ORCH] Pot already full "
#                 f"({current_kg:.3f}kg >= {target_kg}kg) — skipping fill"
#             )
#             program_state.begin_pot_filling()
#             program_state.on_pot_filled()   # → PRESSURISING
#             return

#         self._fill_phase_start_ts = now
#         self._fill_phase_start_weight = current_kg
#         self._fill_last_weight = current_kg
#         self._fill_last_weight_ts = now

#         program_state.begin_pot_filling()
#         print(
#             f"[STARTUP_ORCH] begin() — profile={self.profile.name} "
#             f"pot_now={current_kg:.3f}kg "
#             f"target={target_kg}kg"
#         )

#     # ──────────────────────────────────────────────────────────────
#     def process(self):
#         ps = program_state
#         mat = material_state_manager.state
#         ms = machine_state_manager.state

#         if ps.phase == ProgramPhase.POT_FILLING:
#             self._handle_pot_filling(mat)
#         elif ps.phase == ProgramPhase.PRESSURISING:
#             self._handle_pressurising(ms)
#         elif ps.phase == ProgramPhase.LINE_PRIMING:
#             self._handle_line_priming(mat)

#     # ──────────────────────────────────────────────────────────────
#     # PHASE 1: POT FILLING
#     #
#     # Full pressure-assisted sequence. Each step is ACK-gated through
#     # create_and_queue_command — the executor ensures each command
#     # completes before the next tick advances the flag.
#     #
#     # Step flags advance one per process() call:
#     #   _fill_depressurised_pot → _fill_res_pressurised →
#     #   _fill_inlet_opened → _fill_vent_opened →
#     #   [FILLING — monitor weight] →
#     #   _fill_inlet_closed → _fill_vent_closed →
#     #   _fill_res_depressurised → [SETTLING] → on_pot_filled()
#     # ──────────────────────────────────────────────────────────────
#     def _handle_pot_filling(self, mat):
#         from app.commands.helpers import create_and_queue_command
#         p = self.profile
#         now = time.time()

#         current_kg = mat.current_pot_kg or 0.0
#         # weight_valid = mat.current_pot_kg is not None and mat.current_pot_kg > 0
#         weight_valid = mat.current_pot_kg is not None and mat.current_pot_kg > 0
#         current_kg = mat.current_pot_kg if mat.current_pot_kg is not None else 0.0

#         # ── 1. Vent pot to atmospheric ─────────────────────────────
#         # Must happen before pressurising reservoir.
#         # If pot is at any residual pressure, the differential needed
#         # to push thick paste through the inlet is reduced or reversed.
#         if not self._fill_depressurised_pot:
#             print("[STARTUP_ORCH] Fill step 1 — venting pot to atmospheric")
#             create_and_queue_command(
#                 name="pot.depressurise",
#                 payload={}
#             )
#             self._fill_depressurised_pot = True
#             return

#         # ── 2. Pressurise reservoir ────────────────────────────────
#         # Required for thick paste — gravity alone won't move it.
#         # pressurise_open_s * 5000ms: reservoir has larger volume than
#         # pot, needs longer to reach working pressure.
#         # Tune pressurise_open_s in PaintProfile per paint viscosity.
#         if not self._fill_res_pressurised:
#             res_open_ms = int(p.pressurise_open_s * 5000)
#             print(
#                 f"[STARTUP_ORCH] Fill step 2 — pressurising reservoir "
#                 f"({res_open_ms}ms)"
#             )
#             create_and_queue_command(
#                 name="res.pressurise",
#                 payload={"open_ms": res_open_ms}
#             )
#             self._fill_res_pressurised = True
#             return

#         # ── 3. Open paint inlet ────────────────────────────────────
#         if not self._fill_inlet_opened:
#             print(
#                 f"[STARTUP_ORCH] Fill step 3 — opening inlet "
#                 f"(target={p.pot_fill_target_kg}kg)"
#             )
#             create_and_queue_command(
#                 name="pot.fill_start",
#                 payload={"target_kg": p.pot_fill_target_kg}
#             )
#             self._fill_inlet_opened = True
#             self._fill_phase_start_ts = now
#             self._fill_last_weight = current_kg
#             self._fill_last_weight_ts = now
#             return

#         # ── 4. Open pot vent ───────────────────────────────────────
#         # Holds pot_air_out open throughout fill.
#         # As thick paste enters, it displaces pot headspace air.
#         # Without this vent open, headspace compresses and builds
#         # back-pressure that fights reservoir pressure → flow stalls.
#         # With vent open, headspace stays near atmospheric the whole
#         # fill — only resistance is viscosity (constant throughout).
#         if not self._fill_vent_opened:
#             print("[STARTUP_ORCH] Fill step 4 — opening pot vent (holds open during fill)")
#             create_and_queue_command(
#                 name="pot.vent_open",
#                 payload={}
#             )
#             self._fill_vent_opened = True
#             return

#         # ── Settling phase after close ─────────────────────────────
#         if self._fill_res_depressurised:
#             settle_elapsed = now - self._settle_start_ts
#             if settle_elapsed >= p.pot_fill_settle_s:
#                 print(
#                     f"[STARTUP_ORCH] Fill settle done ({settle_elapsed:.1f}s) "
#                     f"final={current_kg:.3f}kg → pressurising"
#                 )
#                 program_state.on_pot_filled()  # → PRESSURISING
#             return

#         # ── 8. Depressurise reservoir after fill ───────────────────
#         if self._fill_vent_closed:
#             print("[STARTUP_ORCH] Fill step 8 — depressurising reservoir")
#             create_and_queue_command(
#                 name="res.depressurise",
#                 payload={}
#             )
#             self._fill_res_depressurised = True
#             self._settle_start_ts = now
#             return

#         # ── 7. Close vent second ───────────────────────────────────
#         # Inlet is confirmed closed. Safe to close vent now —
#         # no reservoir pressure can slug paint into sealed pot.
#         if self._fill_inlet_closed:
#             print("[STARTUP_ORCH] Fill step 7 — closing pot vent")
#             create_and_queue_command(
#                 name="pot.vent_close",
#                 payload={}
#             )
#             self._fill_vent_closed = True
#             return

#         # ── 5 & 6. Monitor fill + close inlet when done ────────────
#         # Both paint_inlet and pot_air_out are open.
#         # Watch weight rise to target.

#         elapsed = now - self._fill_phase_start_ts
#         weight_gained = current_kg - self._fill_phase_start_weight

#         # Stall detection
#         if abs(current_kg - self._fill_last_weight) > 0.005:
#             self._fill_last_weight = current_kg
#             self._fill_last_weight_ts = now
#         time_since_change = now - self._fill_last_weight_ts

#         # Time-based fallback if weight sensor invalid
#         if not weight_valid:
#             if elapsed >= p.pot_fill_open_time_s:
#                 print("[STARTUP_ORCH] Weight invalid — closing inlet (time-based)")
#                 create_and_queue_command(name="pot.fill_stop", payload={})
#                 self._fill_inlet_closed = True
#             return

#         # Stall abort
#         if elapsed > p.pot_fill_total_timeout_s and time_since_change > 10.0:
#             print(
#                 f"[STARTUP_ORCH] ABORT: Fill stalled — "
#                 f"no change for {time_since_change:.0f}s "
#                 f"(gained {weight_gained:.3f}kg)"
#             )
#             create_and_queue_command(name="pot.fill_stop", payload={})
#             create_and_queue_command(name="pot.vent_close", payload={})
#             create_and_queue_command(name="res.depressurise", payload={})
#             program_state.abort("pot_fill_stalled")
#             return

#         # Target reached — close inlet FIRST (step 6)
#         # Close inlet before vent: if vent closed first while inlet open,
#         # residual reservoir pressure forces a slug of paint into sealed pot.
#         if current_kg >= p.pot_fill_target_kg:
#             print(
#                 f"[STARTUP_ORCH] Fill step 6 — target reached ({current_kg:.3f}kg), "
#                 f"closing inlet first"
#             )
#             create_and_queue_command(name="pot.fill_stop", payload={})
#             self._fill_inlet_closed = True
#             return

#         # Progress log every 5s
#         if int(elapsed) % 5 == 0 and int(elapsed) > 0:
#             print(
#                 f"[STARTUP_ORCH] Filling: {current_kg:.3f}kg / "
#                 f"{p.pot_fill_target_kg}kg "
#                 f"(+{weight_gained:.3f}kg in {elapsed:.0f}s)"
#             )

#     # ──────────────────────────────────────────────────────────────
#     # PHASE 2: PRESSURISATION
#     # Time-based. Pressure sensor = safety guard only.
#     # ──────────────────────────────────────────────────────────────
#     def _handle_pressurising(self, ms):
#         from app.commands.helpers import create_and_queue_command
#         p = self.profile
#         now = time.time()

#         if not self._pressurise_cmd_sent:
#             open_ms = int(p.pressurise_open_s * 1000)
#             print(
#                 f"[STARTUP_ORCH] Pressurising pot — "
#                 f"open_ms={open_ms} profile={p.name}"
#             )
#             create_and_queue_command(
#                 name="pot.pressurise",
#                 payload={"open_ms": open_ms}
#             )
#             self._pressurise_cmd_sent = True
#             self._pressurise_start_ts = now
#             return

#         elapsed = now - self._pressurise_start_ts
#         pressure = ms.pressure

#         if pressure >= p.pressurise_safety_bar:
#             print(
#                 f"[STARTUP_ORCH] ABORT: Overpressure "
#                 f"({pressure:.2f} bar >= {p.pressurise_safety_bar} bar)"
#             )
#             create_and_queue_command(name="pot.depressurise", payload={})
#             program_state.abort("overpressure")
#             return

#         if elapsed >= p.pressurise_max_open_s:
#             print(f"[STARTUP_ORCH] Pressurise max time reached ({elapsed:.1f}s)")
#             self._complete_pressurisation()
#             return

#         if elapsed >= p.pressurise_open_s:
#             print(
#                 f"[STARTUP_ORCH] Pressurise nominal time done ({elapsed:.1f}s) "
#                 f"→ line priming"
#             )
#             self._complete_pressurisation()

#     def _complete_pressurisation(self):
#         mat = material_state_manager.state
#         now = time.time()
#         program_state.on_pressurised()  # → LINE_PRIMING
#         self._prime_start_ts = now
#         self._prime_start_weight = mat.current_pot_kg
#         self._rate_window_start_ts = now
#         self._rate_window_start_weight = mat.current_pot_kg
#         self._peak_drop_rate = 0.0
#         self._nozzle_cracked = False
#         self._nozzle_crack_ts = 0.0
#         print(
#             f"[STARTUP_ORCH] Pressurisation complete — "
#             f"starting line prime from {mat.current_pot_kg:.3f}kg "
#             f"mode={self.profile.line_prime_mode}"
#         )

#     # ──────────────────────────────────────────────────────────────
#     # PHASE 3: LINE PRIMING
#     # ──────────────────────────────────────────────────────────────
#     def _handle_line_priming(self, mat):
#         from app.commands.helpers import create_and_queue_command
#         p = self.profile
#         now = time.time()

#         weight_valid = mat.current_pot_kg is not None and mat.current_pot_kg > 0

#         if not self._prime_cmd_sent:
#             print(
#                 f"[STARTUP_ORCH] Opening dispense valve — priming line "
#                 f"(mode={p.line_prime_mode} "
#                 f"min={p.line_prime_min_time_s}s "
#                 f"timeout={p.line_prime_timeout_s}s)"
#             )
#             create_and_queue_command(
#                 name="line.prime_start",
#                 payload={"timeout_ms": int(p.line_prime_timeout_s * 1000)}
#             )
#             self._prime_cmd_sent = True
#             self._prime_start_ts = now
#             self._prime_start_weight = mat.current_pot_kg
#             self._rate_window_start_ts = now
#             self._rate_window_start_weight = mat.current_pot_kg
#             return

#         elapsed = now - self._prime_start_ts

#         # Fallback: weight invalid → time-based
#         if not weight_valid:
#             if not self._prime_stop_sent and elapsed >= p.line_prime_min_time_s:
#                 print("[STARTUP_ORCH] Weight invalid — assuming primed (time-based)")
#                 create_and_queue_command(name="line.prime_stop", payload={})
#                 self._prime_stop_sent = True
#                 program_state.on_line_primed()
#                 material_state_manager.state.line_primed = True
#             return

#         total_drain_kg = self._prime_start_weight - mat.current_pot_kg

#         # Hard timeout
#         if elapsed > p.line_prime_timeout_s:
#             print(
#                 f"[STARTUP_ORCH] ABORT: Prime timeout after {elapsed:.0f}s "
#                 f"({total_drain_kg*1000:.0f}g drained)"
#             )
#             create_and_queue_command(name="line.prime_stop", payload={})
#             program_state.abort("line_prime_timeout")
#             return

#         # Safety drain cap — applies to both modes
#         if total_drain_kg >= p.line_prime_max_drain_kg:
#             print(
#                 f"[STARTUP_ORCH] ABORT: Prime drain cap — "
#                 f"{total_drain_kg:.3f}kg drained (max={p.line_prime_max_drain_kg}kg)"
#             )
#             create_and_queue_command(name="line.prime_stop", payload={})
#             program_state.abort("line_prime_excess_drain")
#             return

#         if p.line_prime_mode == "open_pipe":
#             self._prime_open_pipe(mat, elapsed, total_drain_kg, now, p)
#         else:
#             self._prime_spring_nozzle(mat, elapsed, total_drain_kg, now, p)

#     def _prime_open_pipe(self, mat, elapsed, total_drain_kg, now, p):
#         """
#         Open pipe detection.
#         Prime complete when total drain >= pipe volume AND flow is active.
#         No crack event — flow is constant from the moment pressure applied.
#         """
#         from app.commands.helpers import create_and_queue_command

#         rate_window_elapsed = now - self._rate_window_start_ts
#         current_rate = 0.0

#         if rate_window_elapsed >= p.line_prime_rate_window_s and rate_window_elapsed > 0:
#             weight_in_window = self._rate_window_start_weight - mat.current_pot_kg
#             current_rate = weight_in_window / rate_window_elapsed
#             self._rate_window_start_ts = now
#             self._rate_window_start_weight = mat.current_pot_kg

#         print(
#             f"[STARTUP_ORCH] Prime (open_pipe): elapsed={elapsed:.0f}s "
#             f"drained={total_drain_kg*1000:.0f}g / "
#             f"{p.line_prime_line_volume_kg*1000:.0f}g needed "
#             f"rate={current_rate*1000:.1f}g/s"
#         )

#         if elapsed < p.line_prime_min_time_s:
#             return

#         if total_drain_kg < p.line_prime_line_volume_kg:
#             return

#         # Confirm active flow — not just sensor noise
#         if current_rate <= 0.002:
#             return

#         print(
#             f"[STARTUP_ORCH] Line PRIMED (open_pipe) — "
#             f"drained={total_drain_kg*1000:.0f}g "
#             f"rate={current_rate*1000:.1f}g/s "
#             f"elapsed={elapsed:.1f}s"
#         )

#         if not self._prime_stop_sent:
#             create_and_queue_command(name="line.prime_stop", payload={})
#             self._prime_stop_sent = True
#             program_state.on_line_primed()
#             material_state_manager.state.line_primed = True

#     def _prime_spring_nozzle(self, mat, elapsed, total_drain_kg, now, p):
#         """
#         Spring nozzle detection.
#         Prime complete when nozzle crack rate spike detected.
#         """
#         from app.commands.helpers import create_and_queue_command

#         rate_window_elapsed = now - self._rate_window_start_ts
#         if rate_window_elapsed < p.line_prime_rate_window_s:
#             return

#         if rate_window_elapsed <= 0:
#             return

#         weight_in_window = self._rate_window_start_weight - mat.current_pot_kg
#         current_rate = weight_in_window / rate_window_elapsed

#         if current_rate > self._peak_drop_rate:
#             self._peak_drop_rate = current_rate

#         self._rate_window_start_ts = now
#         self._rate_window_start_weight = mat.current_pot_kg

#         print(
#             f"[STARTUP_ORCH] Prime (spring_nozzle): elapsed={elapsed:.0f}s "
#             f"drained={total_drain_kg*1000:.0f}g "
#             f"rate={current_rate*1000:.1f}g/s "
#             f"threshold={p.line_prime_nozzle_crack_rate_kg_s*1000:.1f}g/s"
#         )

#         if not self._nozzle_cracked:
#             if current_rate >= p.line_prime_nozzle_crack_rate_kg_s:
#                 self._nozzle_cracked = True
#                 self._nozzle_crack_ts = now
#                 print(f"[STARTUP_ORCH] Nozzle crack at t={elapsed:.0f}s")

#         if not self._nozzle_cracked:
#             return

#         if elapsed < p.line_prime_min_time_s:
#             return

#         if total_drain_kg >= 0.7:
#             print(f"[STARTUP_ORCH] SAFETY: Excess drain {total_drain_kg:.3f}kg")
#             if not self._prime_stop_sent:
#                 create_and_queue_command(name="line.prime_stop", payload={})
#                 self._prime_stop_sent = True
#                 program_state.abort("line_prime_excess_drain")
#             return

#         print(
#             f"[STARTUP_ORCH] Line PRIMED (spring_nozzle) — "
#             f"elapsed={elapsed:.1f}s drain={total_drain_kg*1000:.0f}g"
#         )

#         if not self._prime_stop_sent:
#             create_and_queue_command(name="line.prime_stop", payload={})
#             self._prime_stop_sent = True
#             program_state.on_line_primed()
#             material_state_manager.state.line_primed = True


# startup_orchestrator = StartupOrchestrator()

# app/orchestrators/startup_orchestrator.py

import json
import time
from app.state.program_state import program_state, ProgramPhase
from app.state.material_state import material_state_manager
from app.state.machine_state import machine_state_manager
from app.config.paint_profile import PaintProfile, DEFAULT_PROFILE
# from app.services.command_executor import executor


class StartupOrchestrator:
    """
    Drives the startup sequence:
        STARTUP → POT_FILLING → PRESSURISING → LINE_PRIMING → READY

    All timing comes from the PaintProfile injected at begin().
    Call reset() + begin(profile) at the start of every new program.
    """

    def __init__(self):
        self.profile: PaintProfile = DEFAULT_PROFILE
        self._reset_state()

    def _reset_state(self):
        # Fill phase
        self._fill_cmd_sent = False
        self._fill_stop_sent = False
        self._fill_phase_start_ts = 0.0
        self._fill_phase_start_weight = 0.0
        self._fill_last_weight = 0.0
        self._fill_last_weight_ts = 0.0
        self._settle_start_ts = 0.0

        # Pressurise phase
        self._pressurise_cmd_sent = False
        self._pressurise_start_ts = 0.0

        # Line prime phase
        self._prime_cmd_sent = False
        self._prime_stop_sent = False

        self._prime_start_ts = 0.0
        self._prime_start_weight = 0.0
        self._rate_window_start_ts = 0.0
        self._rate_window_start_weight = 0.0
        self._peak_drop_rate = 0.0
        self._nozzle_crack_ts = 0.0
        self._nozzle_cracked = False

    def reset(self):
        """Call at program start to wipe all one-shot flags."""
        self._reset_state()
        print("[STARTUP_ORCH] Reset")

    def _emit_event(self, event_name: str):
        payload = {
            "event": event_name
        }
        self.client.publish("devices/edge1/events", json.dumps(payload))

    def begin(self, profile: PaintProfile = None):
        """
        Called once when startup.sequence ACK completes.
        Transitions STARTUP → POT_FILLING and sets the profile for this run.
        """
        if profile:
            self.profile = profile

        mat = material_state_manager.state
        now = time.time()

        # Ignore invalid weight
        # if mat.current_pot_kg <= 0:
        #     return

        # current_kg = mat.current_pot_kg or 0.0

        current_kg = mat.current_pot_kg or 0.0
        target_kg = self.profile.pot_fill_target_kg

        # ─────────────────────────────────────────
        # 1️⃣ Skip fill if already above target
        # ─────────────────────────────────────────
        if current_kg >= target_kg:

            from app.commands.helpers import create_and_queue_command

            print(
                f"[STARTUP_ORCH] Pot already above target "
                f"({current_kg:.3f}kg >= {target_kg}kg) — skipping fill"
            )    
            create_and_queue_command(name="pot.fill_stop", payload={})
            # create_and_queue_command(name="pot.fill_stop", payload={})
            program_state.begin_pot_filling()   # enter POT_FILLING first
            program_state.on_pot_filled()   # → PRESSURISING
            return


        # if mat.current_pot_kg >= self.profile.pot_fill_target_kg:
        #     print("[STARTUP_ORCH] Pot already above target — skipping fill")
        #     program_state.on_pot_filled()
        #     return
        


        self._fill_phase_start_ts = now
        self._fill_phase_start_weight = current_kg
        self._fill_last_weight = current_kg
        self._fill_last_weight_ts = now
        self._fill_cmd_sent = False
        self._fill_stop_sent = False

        program_state.begin_pot_filling()
        print(
            f"[STARTUP_ORCH] begin() — profile={self.profile.name} "
            f"pot_now={mat.current_pot_kg:.3f}kg "
            f"target={self.profile.pot_fill_target_kg}kg"
        )

    # ──────────────────────────────────────────────────────────────
    # Called every telemetry tick from state_orchestrator
    # ──────────────────────────────────────────────────────────────
    def process(self):
        ps = program_state
        mat = material_state_manager.state
        ms = machine_state_manager.state

        if ps.phase == ProgramPhase.POT_FILLING:
            self._handle_pot_filling(mat)
        elif ps.phase == ProgramPhase.PRESSURISING:
            self._handle_pressurising(ms)
        elif ps.phase == ProgramPhase.LINE_PRIMING:
            self._handle_line_priming(mat)

    # ──────────────────────────────────────────────────────────────
    # PHASE 1: POT FILLING
    # Primary signal: pot_weight rising
    # ──────────────────────────────────────────────────────────────
    def _handle_pot_filling(self, mat):
        weight_valid = mat.current_pot_kg is not None and mat.current_pot_kg > 0

        from app.commands.helpers import create_and_queue_command
        p = self.profile
        now = time.time()

        current_kg = mat.current_pot_kg

        print("DEBUG POT_FILLING tick", mat.current_pot_kg)

        if not self._fill_cmd_sent:
            print(f"[STARTUP_ORCH] Opening paint_inlet — target={p.pot_fill_target_kg}kg")
            create_and_queue_command(
                name="pot.fill_start",
                payload={"target_kg": p.pot_fill_target_kg}
            )
            self._fill_cmd_sent = True
            self._fill_phase_start_ts = now
            self._fill_phase_start_weight = current_kg
            self._fill_last_weight = current_kg
            self._fill_last_weight_ts = now
            return

        # ── Step 2: Already sent fill_stop — wait for weight to settle ──
        if self._fill_stop_sent:
            settle_elapsed = now - self._settle_start_ts
            if settle_elapsed >= p.pot_fill_settle_s:
                print(
                    f"[STARTUP_ORCH] Pot fill settle done ({settle_elapsed:.1f}s) "
                    f"final={current_kg:.3f}kg → pressurising"
                )
                program_state.on_pot_filled()  # → PRESSURISING
                self._pressurise_start_ts = now
            return

        # ── Track weight change over time ──
        weight_gained_total = current_kg - self._fill_phase_start_weight
        elapsed_total = now - self._fill_phase_start_ts

        # Update last-seen weight tracker
        if current_kg != self._fill_last_weight:
            self._fill_last_weight = current_kg
            self._fill_last_weight_ts = now

        time_since_last_change = now - self._fill_last_weight_ts

        # ── Early flow-start check: if weight hasn't moved at all ──
        elapsed_since_start = now - self._fill_phase_start_ts
        # if elapsed_since_start > p.pot_fill_flow_start_timeout_s:
        #     if weight_gained_total < p.pot_fill_min_gain_kg:
        #         print(
        #             f"[STARTUP_ORCH] ABORT: Pot fill — no flow detected after "
        #             f"{elapsed_since_start:.0f}s (gained {weight_gained_total:.3f}kg)"
        #         )
        #         create_and_queue_command(name="pot.fill_stop", payload={})
        #         program_state.abort("pot_fill_no_flow")
        #         return

        if not weight_valid:
            if not self._fill_stop_sent and elapsed_since_start >= p.pot_fill_open_time_s:
                print("[STARTUP_ORCH] Weight invalid — closing inlet (time-based)")
                create_and_queue_command(name="pot.fill_stop", payload={})
                self._fill_stop_sent = True
                self._settle_start_ts = now
            return

        # ── Total timeout with progressive extension ──
        if elapsed_since_start > p.pot_fill_total_timeout_s:
            if time_since_last_change > 10.0:
                # Weight stopped moving — assume blocked or reservoir empty
                print(
                    f"[STARTUP_ORCH] ABORT: Pot fill stalled — "
                    f"no weight change for {time_since_last_change:.0f}s"
                )
                create_and_queue_command(name="pot.fill_stop", payload={})
                program_state.abort("pot_fill_stalled")
                return
            # Weight still moving but slowly — log and continue
            print(
                f"[STARTUP_ORCH] Pot fill slow — {current_kg:.3f}kg "
                f"(+{weight_gained_total:.3f}kg in {elapsed_since_start:.0f}s)"
            )

        # ── Target reached ──
        if current_kg >= p.pot_fill_target_kg:
            print(
                f"[STARTUP_ORCH] Pot filled ({current_kg:.3f}kg) — "
                f"closing inlet, settling {p.pot_fill_settle_s}s"
            )
            create_and_queue_command(name="pot.fill_stop", payload={})
            self._fill_stop_sent = True
            self._settle_start_ts = now
            return

        # ── Progress log every 5s ──
        if int(elapsed_since_start) % 5 == 0 and int(elapsed_since_start) > 0:
            print(
                f"[STARTUP_ORCH] Filling: {current_kg:.3f}kg / {p.pot_fill_target_kg}kg "
                f"(+{weight_gained_total:.3f}kg in {elapsed_since_start:.0f}s)"
            )

    # ──────────────────────────────────────────────────────────────
    # PHASE 2: PRESSURISATION
    # Time-based primary. Pressure sensor = safety guard only.
    # ──────────────────────────────────────────────────────────────
    def _handle_pressurising(self, ms):
        from app.commands.helpers import create_and_queue_command
        p = self.profile
        now = time.time()

        # ── Send pressurise command once ──
        if not self._pressurise_cmd_sent:
            open_ms = int(p.pressurise_open_s * 1000)
            print(
                f"[STARTUP_ORCH] Pressurising pot — "
                f"open_ms={open_ms} profile={p.name}"
            )
            create_and_queue_command(
                name="pot.pressurise",
                payload={"open_ms": open_ms}
            )
            self._pressurise_cmd_sent = True
            self._pressurise_start_ts = now
            return

        elapsed = now - self._pressurise_start_ts
        pressure = ms.pressure   # may be unreliable — used for safety only

        # ── Safety: overpressure guard ──
        if pressure >= p.pressurise_safety_bar:
            print(
                f"[STARTUP_ORCH] ABORT: Overpressure detected "
                f"({pressure:.2f} bar >= {p.pressurise_safety_bar} bar)"
            )
            create_and_queue_command(name="pot.depressurise", payload={})
            program_state.abort("overpressure")
            return

        # ── Hard max time ceiling ──
        if elapsed >= p.pressurise_max_open_s:
            print(
                f"[STARTUP_ORCH] Pressurise max time reached ({elapsed:.1f}s) — proceeding"
            )
            self._complete_pressurisation()
            return

        # ── Primary: nominal open time elapsed ──
        if elapsed >= p.pressurise_open_s:
            print(
                f"[STARTUP_ORCH] Pressurise nominal time done ({elapsed:.1f}s) "
                f"pressure_reading={pressure:.2f} bar (not trusted as gate) → priming line"
            )
            self._complete_pressurisation()

    def _complete_pressurisation(self):
        mat = material_state_manager.state
        now = time.time()
        program_state.on_pressurised()  # → LINE_PRIMING
        self._prime_start_ts = now
        self._prime_start_weight = mat.current_pot_kg
        self._rate_window_start_ts = now
        self._rate_window_start_weight = mat.current_pot_kg
        self._peak_drop_rate = 0.0
        self._nozzle_cracked = False
        self._nozzle_crack_ts = 0.0
        print(
            f"[STARTUP_ORCH] Pressurisation complete — "
            f"starting line prime from {mat.current_pot_kg:.3f}kg"
        )

    # ──────────────────────────────────────────────────────────────
    # PHASE 3: LINE PRIMING
    #
    # Physical sequence in your 5ft × 1/2" + spring nozzles system:
    #   Phase A: Air in line exits — very low weight drop (air has no mass)
    #   Phase B: Paint fills line slowly — steady weight drop
    #   Phase C: Nozzles crack open — weight drop rate INCREASES briefly
    #   Phase D: Stable flow — rate settles at ongoing dispense rate = PRIMED
    #
    # Detection: watch for rate to increase above nozzle_crack_rate_kg_s,
    # then confirm it stays elevated for stable_confirm_s.
    # ──────────────────────────────────────────────────────────────
    def _handle_line_priming(self, mat):

        weight_valid = (
            mat.current_pot_kg is not None
            and mat.current_pot_kg > 0
        )
        
        from app.commands.helpers import create_and_queue_command
        p = self.profile
        now = time.time()

        # ── Send prime_start once ──
        if not self._prime_cmd_sent:
            print(
                f"[STARTUP_ORCH] Opening dispense valve — priming line "
                f"(profile={p.name}, min={p.line_prime_min_time_s}s, "
                f"timeout={p.line_prime_timeout_s}s)"
            )
            create_and_queue_command(
                name="line.prime_start",
                payload={"timeout_ms": int(p.line_prime_timeout_s * 1000)}
            )
            self._prime_cmd_sent = True
            self._prime_start_ts = now
            self._prime_start_weight = mat.current_pot_kg
            self._rate_window_start_ts = now
            self._rate_window_start_weight = mat.current_pot_kg
            return

        elapsed = now - self._prime_start_ts

        # ─────────────────────────────────────────
        # Fallback: weight invalid → time-based prime
        # ─────────────────────────────────────────
        if not weight_valid:
            if (
                not self._prime_stop_sent
                and elapsed >= p.line_prime_min_time_s
            ):
                print("[STARTUP_ORCH] Weight invalid — assuming primed (time-based)")
                create_and_queue_command(name="line.prime_stop", payload={})
                # self._emit_event("line.prime_stop")
                self._prime_stop_sent = True
                program_state.on_line_primed()
                material_state_manager.state.line_primed = True
            return
        total_drain_kg = self._prime_start_weight - mat.current_pot_kg

        # ── Hard timeout ──
        # if elapsed > p.line_prime_timeout_s:
        #     print(
        #         f"[STARTUP_ORCH] ABORT: Line prime timeout after {elapsed:.0f}s "
        #         f"({total_drain_kg*1000:.0f}g drained)"
        #     )
        #     create_and_queue_command(name="line.prime_stop", payload={})
        #     program_state.abort("line_prime_timeout")
        #     return

        # ── Safety drain cap ──
        # if total_drain_kg >= p.line_prime_max_drain_kg:
        #     print(
        #         f"[STARTUP_ORCH] ABORT: Line prime safety cap — "
        #         f"{total_drain_kg:.3f}kg drained (max={p.line_prime_max_drain_kg}kg)"
        #     )
        #     create_and_queue_command(name="line.prime_stop", payload={})
        #     program_state.abort("line_prime_excess_drain")
        #     return

        # ── Compute rate every rate_window_s ──
        rate_window_elapsed = now - self._rate_window_start_ts
        if rate_window_elapsed < p.line_prime_rate_window_s:
            return   # not time to sample yet

        weight_in_window = self._rate_window_start_weight - mat.current_pot_kg
        # current_rate = weight_in_window / rate_window_elapsed  # kg/s (positive = drain)

        if rate_window_elapsed <= 0:
            return
        current_rate = weight_in_window / rate_window_elapsed


        # Update peak
        if current_rate > self._peak_drop_rate:
            self._peak_drop_rate = current_rate

        # Reset window
        self._rate_window_start_ts = now
        self._rate_window_start_weight = mat.current_pot_kg

        print(
            f"[STARTUP_ORCH] Line prime: elapsed={elapsed:.0f}s "
            f"drained={total_drain_kg*1000:.0f}g "
            f"rate={current_rate*1000:.1f}g/s "
            f"peak={self._peak_drop_rate*1000:.1f}g/s "
            f"nozzle_crack_threshold={p.line_prime_nozzle_crack_rate_kg_s*1000:.1f}g/s"
        )

        # ── Only check for prime after minimum time ──
        # if elapsed < p.line_prime_min_time_s:
        #     return

        # # ── Nozzle crack detection: rate exceeded threshold ──
        # if not self._nozzle_cracked:
        #     if current_rate >= p.line_prime_nozzle_crack_rate_kg_s:
        #         self._nozzle_cracked = True
        #         self._nozzle_crack_ts = now
        #         print(
        #             f"[STARTUP_ORCH] Nozzle crack detected — "
        #             f"rate={current_rate*1000:.1f}g/s at t={elapsed:.0f}s"
        #         )
        #     return  # wait for crack before confirming

        # ── Detect crack immediately (do NOT wait for min time) ──
        if not self._nozzle_cracked:
            if current_rate >= p.line_prime_nozzle_crack_rate_kg_s:
                self._nozzle_cracked = True
                self._nozzle_crack_ts = now
                print(
                    f"[STARTUP_ORCH] Nozzle crack detected — "
                    f"rate={current_rate*1000:.1f}g/s at t={elapsed:.0f}s"
                )

        # # If crack not yet detected → cannot finish
        # if not self._nozzle_cracked:
        #     return

        # Only allow completion AFTER minimum prime time
        if elapsed < p.line_prime_min_time_s:
            return


        # ─────────────────────────────────────────
        # HARD DRAIN SAFETY (industrial protection)
        # ─────────────────────────────────────────

        # if total_drain_kg >= 0.7:   # 700g max physical allowance
        #     print(
        #         f"[STARTUP_ORCH] SAFETY: Excess drain "
        #         f"{total_drain_kg:.3f}kg — closing prime valve"
        #     )

        #     if not self._prime_stop_sent:
        #         create_and_queue_command(name="line.prime_stop", payload={})
        #         self._prime_stop_sent = True
        #         program_state.abort("line_prime_excess_drain")

        #     return

        # ─────────────────────────────────────────
        # Finish priming immediately after:
        #   1) Nozzle crack detected
        #   2) Minimum prime time satisfied
        # ─────────────────────────────────────────

        if self._nozzle_cracked and elapsed >= p.line_prime_min_time_s:

            print(
                f"[STARTUP_ORCH] Line PRIMED — "
                f"crack_detected elapsed={elapsed:.1f}s "
                f"total_drain={total_drain_kg*1000:.0f}g"
            )

            if not self._prime_stop_sent:
                create_and_queue_command(name="line.prime_stop", payload={})
                self._prime_stop_sent = True
                program_state.on_line_primed()
                material_state_manager.state.line_primed = True

            return


        # ── Confirm stable flow after crack ──
        # time_since_crack = now - self._nozzle_crack_ts
        # if time_since_crack >= p.line_prime_stable_confirm_s:
        #     print(
        #         f"[STARTUP_ORCH] Line PRIMED — "
        #         f"stable for {time_since_crack:.1f}s after nozzle crack "
        #         f"total_drain={total_drain_kg*1000:.0f}g elapsed={elapsed:.0f}s"
        #     )
        #     # create_and_queue_command(name="line.prime_stop", payload={})
        #     # program_state.on_line_primed()   # → READY
        #     # material_state_manager.state.line_primed = True

        #     if not hasattr(self, "_prime_stop_sent"):
        #         self._prime_stop_sent = False

        #     if not self._prime_stop_sent:
        #         create_and_queue_command(name="line.prime_stop", payload={})
        #         self._prime_stop_sent = True
        #         program_state.on_line_primed()
        #         material_state_manager.state.line_primed = True



startup_orchestrator = StartupOrchestrator()
