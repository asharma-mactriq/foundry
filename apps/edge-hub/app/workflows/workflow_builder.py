# app/workflows/workflow_builder.py
#
# Converts high-level Edge commands (pressure.reprime, purge.nozzle, refill.start)
# into low-level Workflow JSON for the runtime.
#
import uuid  # <--- Add this line
import json
# ... other imports
from typing import Dict, Any
from app.state.program_state import program_state



DEVICE_MAP = {
    "valves": {
        "dispense": 1,
        "paint_inlet": 2,
        "pot_air_in": 3,
        "pot_air_out": 4,
        "res_air_in": 5,
        "res_air_out": 6,
    }
}

def _build_demo_workflow(payload: Dict[str, Any], cmd_id: str) -> Dict[str, Any]:
    valves = DEVICE_MAP["valves"]

    refill_time = int(payload.get("refill_ms", 3000))
    prime_time = int(payload.get("prime_ms", 4000))

    steps = [
        # ------------------------------------------------
        # LIFECYCLE START
        # ------------------------------------------------
        {"type": "CMD_ACK_RECEIVED"},
        {"type": "CMD_ACK_STARTED"},

        # ------------------------------------------------
        # PHASE 1 — CREATE PRESSURE DIFFERENTIAL
        # ------------------------------------------------
        {"type": "EMIT_EVENT", "eventName": "prep_differential_start"},

        # Vent pot
        {"type": "OPEN_VALVE", "valveId": valves["pot_air_out"]},
        {"type": "WAIT_MS", "durationMs": 2000},
        {"type": "CLOSE_VALVE", "valveId": valves["pot_air_out"]},
        {"type": "WAIT_MS", "durationMs": 1000},

        # Pressurise reservoir
        {"type": "OPEN_VALVE", "valveId": valves["res_air_in"]},
        {"type": "WAIT_MS", "durationMs": 4000},
        {"type": "CLOSE_VALVE", "valveId": valves["res_air_in"]},
        {"type": "WAIT_MS", "durationMs": 1000},

        # ------------------------------------------------
        # PHASE 2 — PRESSURE-ASSISTED REFILL
        # ------------------------------------------------
        {"type": "EMIT_EVENT", "eventName": "refill_active"},
        {"type": "OPEN_VALVE", "valveId": valves["paint_inlet"]},
        {"type": "WAIT_MS", "durationMs": refill_time},
        {"type": "CLOSE_VALVE", "valveId": valves["paint_inlet"]},
        {"type": "WAIT_MS", "durationMs": 1000},

        # ------------------------------------------------
        # PHASE 3 — PRIME POT FOR OPERATION
        # ------------------------------------------------
        {"type": "EMIT_EVENT", "eventName": "pot_priming"},
        {"type": "OPEN_VALVE", "valveId": valves["pot_air_in"]},
        {"type": "WAIT_MS", "durationMs": prime_time},
        {"type": "CLOSE_VALVE", "valveId": valves["pot_air_in"]},
        {"type": "WAIT_MS", "durationMs": 1000},

        # ------------------------------------------------
        # PHASE 4 — DISPENSE TEST SHOT
        # ------------------------------------------------
        {"type": "EMIT_EVENT", "eventName": "dispense_active"},
        {"type": "OPEN_VALVE", "valveId": valves["dispense"]},
        {"type": "WAIT_MS", "durationMs": 1400},
        {"type": "CLOSE_VALVE", "valveId": valves["dispense"]},
        {"type": "WAIT_MS", "durationMs": 1000},

        # ------------------------------------------------
        # PHASE 5 — SAFE RESERVOIR
        # ------------------------------------------------
        {"type": "OPEN_VALVE", "valveId": valves["res_air_out"]},
        {"type": "WAIT_MS", "durationMs": 1000},
        {"type": "CLOSE_VALVE", "valveId": valves["res_air_out"]},
        {"type": "WAIT_MS", "durationMs": 1000},

        {"type": "EMIT_EVENT", "eventName": "machine_ready_state"},

        # ------------------------------------------------
        # LIFECYCLE COMPLETE
        # ------------------------------------------------
        {"type": "CMD_ACK_COMPLETED"},
    ]

    return {
        "name": "pressure_assisted_prep",
        "cmd_id": cmd_id,
        "steps": steps
    }


def build_workflow_for_command(cmd_name: str, payload: Dict[str, Any], cmd_id: str) -> Dict[str, Any]:

    steps = []

    # --- Lifecycle headers ---
    steps.append({"type": "CMD_ACK_RECEIVED"})
    steps.append({"type": "CMD_ACK_STARTED"})

    # ------------------------------------------------
    # COMMAND-SPECIFIC STEPS
    # ------------------------------------------------

    if cmd_name == "program.load":
        steps += [
            {"type": "EMIT_EVENT", "eventName": "program_load_begin"},
            {"type": "WAIT_MS", "durationMs": 50},
            {"type": "EMIT_EVENT", "eventName": "program_load_done"},
        ]

    elif cmd_name == "startup.sequence":
        steps += [
            {"type": "EMIT_EVENT", "eventName": "hw_init_start"},
            {"type": "WAIT_MS", "durationMs": 1000},
            {"type": "EMIT_EVENT", "eventName": "hw_init_done"},
        ]

    elif cmd_name == "pot.fill_start":
        steps += [
            {"type": "OPEN_VALVE", "valveId": DEVICE_MAP["valves"]["paint_inlet"]},
            {"type": "EMIT_EVENT", "eventName": "pot_fill_started"},
        ]


    elif cmd_name == "pot.fill_stop":
        steps += [
            {"type": "CLOSE_VALVE", "valveId": DEVICE_MAP["valves"]["paint_inlet"]},
            {"type": "EMIT_EVENT", "eventName": "pot_fill_stopped"},
        ]

    elif cmd_name == "pot.pressurise":
        open_ms = payload.get("open_ms", 12000)
        steps += [
            {"type": "OPEN_VALVE", "valveId": DEVICE_MAP["valves"]["pot_air_in"]},
            {"type": "EMIT_EVENT", "eventName": "pressurise_start"},
            {"type": "WAIT_MS", "durationMs": open_ms},
            {"type": "CLOSE_VALVE", "valveId": DEVICE_MAP["valves"]["pot_air_in"]},
            {"type": "EMIT_EVENT", "eventName": "pressurise_done"},
        ]

    elif cmd_name == "pot.depressurise":
        steps += [
            {"type": "OPEN_VALVE", "valveId": DEVICE_MAP["valves"]["pot_air_out"]},
            {"type": "WAIT_MS", "durationMs": 5000},
            {"type": "CLOSE_VALVE", "valveId": DEVICE_MAP["valves"]["pot_air_out"]},
            {"type": "EMIT_EVENT", "eventName": "depressurise_done"},
        ]

    elif cmd_name == "dispense.open":
        open_ms = payload.get("open_ms", 1000)
        steps += [
            {"type": "OPEN_VALVE", "valveId": DEVICE_MAP["valves"]["dispense"]},
            {"type": "WAIT_MS", "durationMs": open_ms},
            {"type": "CLOSE_VALVE", "valveId": DEVICE_MAP["valves"]["dispense"]},
            {"type": "EMIT_EVENT", "eventName": "dispense_complete"},
        ]

    elif cmd_name == "dispense.stop":
        steps += [
            {"type": "CLOSE_VALVE", "valveId": DEVICE_MAP["valves"]["dispense"]},
            {"type": "EMIT_EVENT", "eventName": "dispense_stopped"},
        ]
    
    elif cmd_name == "res.pressurise":
        open_ms = payload.get("open_ms", 4000)
        steps += [
            {"type": "OPEN_VALVE", "valveId": DEVICE_MAP["valves"]["res_air_in"]},
            {"type": "EMIT_EVENT", "eventName": "res_pressurise_start"},
            {"type": "WAIT_MS", "durationMs": open_ms},
            {"type": "CLOSE_VALVE", "valveId": DEVICE_MAP["valves"]["res_air_in"]},
            {"type": "EMIT_EVENT", "eventName": "res_pressurise_done"},
        ]

    elif cmd_name == "res.depressurise":
        steps += [
            {"type": "OPEN_VALVE", "valveId": DEVICE_MAP["valves"]["res_air_out"]},
            {"type": "WAIT_MS", "durationMs": 2000},
            {"type": "CLOSE_VALVE", "valveId": DEVICE_MAP["valves"]["res_air_out"]},
            {"type": "EMIT_EVENT", "eventName": "res_depressurise_done"},
        ]


    elif cmd_name == "program.stop":
        steps += [
            {"type": "CLOSE_VALVE", "valveId": DEVICE_MAP["valves"]["dispense"]},
            {"type": "CLOSE_VALVE", "valveId": DEVICE_MAP["valves"]["paint_inlet"]},
            {"type": "CLOSE_VALVE", "valveId": DEVICE_MAP["valves"]["pot_air_in"]},
            {"type": "EMIT_EVENT", "eventName": "program_stopped"},
        ]

    elif cmd_name == "system.emergency_stop":
        steps += [
            {"type": "CLOSE_ALL_VALVES"},
            {"type": "EMIT_EVENT", "eventName": "emergency_stop"},
        ]

    elif cmd_name == "demo.run":
        return _build_demo_workflow(payload, cmd_id)
    
    elif cmd_name == "line.prime_start":
        steps += [
            {"type": "OPEN_VALVE", "valveId": DEVICE_MAP["valves"]["dispense"]},
            {"type": "EMIT_EVENT", "eventName": "line_prime_started"},
        ]

    elif cmd_name == "line.prime_stop":
        steps += [
            {"type": "CLOSE_VALVE", "valveId": DEVICE_MAP["valves"]["dispense"]},
            {"type": "EMIT_EVENT", "eventName": "line_prime_stopped"},
        ]


    else:
        print(f"[WORKFLOW] No workflow defined for: {cmd_name}")
        return None

    # --- Lifecycle completion ---
    steps.append({"type": "CMD_ACK_COMPLETED"})

    return {
        "name": cmd_name.replace(".", "_"),
        "cmd_id": cmd_id,
        "steps": steps
    }



# ----------------------------------------------------------------------
# MAIN ENTRY POINT
# ----------------------------------------------------------------------
# def build_workflow_for_command(cmd_name: str, payload: Dict[str, Any], cmd_id: str) -> Dict[str, Any]:
#     """
#     Convert a high-level command into a runtime workflow JSON object.
#     """

#     # if cmd_name == "program.load":
#     #     return {
#     #     "name": "program_load",
#     #     "cmd_id": cmd_id,
#     #     "steps": [
#     #         { "type": "CMD_ACK_RECEIVED" },
#     #         { "type": "CMD_ACK_STARTED" },
#     #         {"type": "EMIT_EVENT", "eventName": "program_load_begin"},
#     #         {"type": "WAIT_MS", "durationMs": 50},
#     #         {"type": "EMIT_EVENT", "eventName": "program_load_done"},
#     #         { "type": "CMD_ACK_COMPLETED" }

#     #     ]
#     # }

#     # # if cmd_name == "program.start":
#     # #     return {
#     # #         "name": "program_start",
#     # #         "cmd_id": cmd_id,
#     # #         "steps": [
#     # #             { "type": "CMD_ACK_RECEIVED" },
#     # #             { "type": "CMD_ACK_STARTED" },
#     # #             {"type": "EMIT_EVENT", "eventName": "program_start_begin"},
#     # #             {"type": "WAIT_MS", "durationMs": 5000},
#     # #             {"type": "EMIT_EVENT", "eventName": "program_start_done"},
#     # #             { "type": "CMD_ACK_COMPLETED" }

#     # #         ]
#     # # }

#     # if cmd_name == "dispense.start":
#     #     return {
#     #         "name": "dispense_start",
#     #         "cmd_id": cmd_id,
#     #         "steps": [
#     #             { "type": "CMD_ACK_RECEIVED" },
#     #             { "type": "CMD_ACK_STARTED" },
#     #             { "type": "OPEN_VALVE", "valveId": 1 },
#     #             { "type": "WAIT_MS", "durationMs": 120 },
#     #             { "type": "CLOSE_VALVE", "valveId": 1 },
#     #             { "type": "CMD_ACK_COMPLETED" }
#     #         ]
#     #     }

#     # if cmd_name == "program.stop":

#     #     # -----------------------------
#     #     # IDEMPOTENCY PROTECTION
#     #     # -----------------------------
#     #     # IDEMPOTENCY PROTECTION
#     #     # -----------------------------
#     #     from app.state.program_state import ProgramPhase
#     #     if program_state.phase == ProgramPhase.STOPPED:
#     #         print("[WORKFLOW] program.stop ignored — already stopped")
#     #         return None

#     #     return {
#     #         "name": "program_stop",
#     #         "cmd_id": cmd_id,
#     #         "steps": [
#     #             { "type": "CMD_ACK_RECEIVED" },
#     #             { "type": "CMD_ACK_STARTED" },
#     #             {"type": "EMIT_EVENT", "eventName": "program_stop_begin"},
#     #             {"type": "WAIT_MS", "durationMs": 50},
#     #             {"type": "EMIT_EVENT", "eventName": "program_stop_done"},
#     #             { "type": "CMD_ACK_COMPLETED" }
#     #         ]
#     #     }

#     # # if cmd_name == "program.stop":
#     # #     return {
#     # #         "name": "program_stop",
#     # #         "cmd_id": cmd_id,
#     # #         "steps": [
#     # #             { "type": "CMD_ACK_RECEIVED" },
#     # #             { "type": "CMD_ACK_STARTED" },
#     # #             {"type": "EMIT_EVENT", "eventName": "program_stop_begin"},
#     # #             {"type": "WAIT_MS", "durationMs": 50},
#     # #             {"type": "EMIT_EVENT", "eventName": "program_stop_done"},
#     # #             { "type": "CMD_ACK_COMPLETED" }
#     # #         ]
#     # # }

#     # if cmd_name == "program.next_pass":
#     #     return {
#     #         "name": "program_next_pass",
#     #         "cmd_id": cmd_id,
#     #         "steps": [
#     #             { "type": "CMD_ACK_RECEIVED" },
#     #             { "type": "CMD_ACK_STARTED" }, 
#     #             {"type": "EMIT_EVENT", "eventName": "program_next_pass_begin"},
#     #             {"type": "WAIT_MS", "durationMs": 50},
#     #             {"type": "EMIT_EVENT", "eventName": "program_next_pass_done"},
#     #             { "type": "CMD_ACK_COMPLETED" }
#     #         ]
#     #     }



#     # # PRESSURE REPRIME
#     # if cmd_name == "pressure.reprime":
#     #     valve = DEVICE_MAP["valves"]["pot_air_in"]
#     #     return {
#     #         "name": "pressure_reprime",
#     #         "cmd_id": cmd_id,
#     #         "steps": [
#     #             { "type": "CMD_ACK_RECEIVED" },
#     #             { "type": "CMD_ACK_STARTED" },
#     #             { "type": "OPEN_VALVE", "valveId": valve },
#     #             { "type": "WAIT_MS", "durationMs": payload.get("duration_ms", 5000) },
#     #             # { "type": "CHECK_PRESSURE", "threshold": payload.get("threshold", 1.5) },
#     #             { "type": "CLOSE_VALVE", "valveId": valve },
#     #             { "type": "EMIT_EVENT", "eventName": "reprime_done" },
#     #             { "type": "CMD_ACK_COMPLETED" }
#     #         ]
#     #     }

#     # # REFILL START
#     # if cmd_name == "refill.start":
#     #     valve = DEVICE_MAP["valves"]["paint_inlet"]
#     #     return {
#     #         "name": "refill_cycle",
#     #         "cmd_id": cmd_id,
#     #         "steps": [
#     #             { "type": "CMD_ACK_RECEIVED" },
#     #             { "type": "CMD_ACK_STARTED" }, 
#     #             {"type": "OPEN_VALVE", "valveId": valve},
#     #             {"type": "WAIT_MS", "durationMs": payload.get("duration_ms", 2000)},
#     #             {"type": "CLOSE_VALVE", "valveId": valve},
#     #             {"type": "EMIT_EVENT", "eventName": "refill_done"},
#     #             { "type": "CMD_ACK_COMPLETED" }

#     #         ]
#     #     }

#     # if cmd_name == "refill.open":
#     #     return {
#     #         "name": "refill_open",
#     #         "cmd_id": cmd_id,
#     #         "steps": [
#     #             {"type": "CMD_ACK_RECEIVED"},
#     #             {"type": "CMD_ACK_STARTED"},
#     #             {"type": "OPEN_VALVE", "valveId": valve},
#     #             {"type": "CMD_ACK_COMPLETED"}
#     #         ]
#     #     }

#     # if cmd_name == "refill.close":
#     #     return {
#     #         "name": "refill_close",
#     #         "cmd_id": cmd_id,
#     #         "steps": [
#     #             {"type": "CMD_ACK_RECEIVED"},
#     #             {"type": "CMD_ACK_STARTED"},
#     #             {"type": "CLOSE_VALVE", "valveId": valve},
#     #             {"type": "CMD_ACK_COMPLETED"}
#     #         ]
#     #     }


#     # # PURGE NOZZLE
#     # if cmd_name == "purge.nozzle":
#     #     valve = DEVICE_MAP["valves"]["dispense"]
#     #     return {
#     #         "name": "purge_nozzle",
#     #         "cmd_id": cmd_id,
#     #         "steps": [
#     #             { "type": "CMD_ACK_RECEIVED" },
#     #             { "type": "CMD_ACK_STARTED" }, 
#     #             {"type": "OPEN_VALVE", "valveId": valve},
#     #             {"type": "WAIT_MS", "durationMs": payload.get("duration_ms", 1000)},
#     #             {"type": "CLOSE_VALVE", "valveId": valve},
#     #             {"type": "EMIT_EVENT", "eventName": "purge_complete"},
#     #             { "type": "CMD_ACK_COMPLETED" }
#     #         ]
#     #     }

#     # # MANUAL DISPENSE OPEN
#     # if cmd_name == "dispense.open":
#     #     dur = payload.get("open_ms", 100)
#     #     return {
#     #         "name": "manual_dispense",
#     #         "cmd_id": cmd_id,
#     #         "steps": [
#     #             { "type": "CMD_ACK_RECEIVED" },
#     #             { "type": "CMD_ACK_STARTED" }, 
#     #             {"type": "OPEN_VALVE", "valveId": DEVICE_MAP["valves"]["dispense"]},
#     #             {"type": "WAIT_MS", "durationMs": dur},
#     #             {"type": "CLOSE_VALVE", "valveId": DEVICE_MAP["valves"]["dispense"]},
#     #             {"type": "EMIT_EVENT", "eventName": "dispense_manual_done"},
#     #             { "type": "CMD_ACK_COMPLETED" }
#     #         ]
#     #     }
    

#     # # Inside app/workflows/workflow_builder.py

#     # if cmd_name == "startup.sequence":
#     #     return {
#     #         "name": "startup_sequence",
#     #         "cmd_id": cmd_id,
#     #         "steps": [
#     #             { "type": "CMD_ACK_RECEIVED" },
#     #             { "type": "CMD_ACK_STARTED" },
#     #             # Example: A 1-second "Hardware Shake" or initialization delay
#     #             {"type": "EMIT_EVENT", "eventName": "hw_init_start"},
#     #             {"type": "WAIT_MS", "durationMs": 1000}, 
#     #             {"type": "EMIT_EVENT", "eventName": "hw_init_done"},


                
#     #             { "type": "CMD_ACK_COMPLETED" }
#     #         ]
#     #     }

#     # if cmd_name == "program.start":
#     #     return {
#     #         "name": "program_start",
#     #         "cmd_id": cmd_id,
#     #         "steps": [
#     #             { "type": "CMD_ACK_RECEIVED" },
#     #             { "type": "CMD_ACK_STARTED" },
#     #             { "type": "EMIT_EVENT", "eventName": "program_started" },
#     #             { "type": "CMD_ACK_COMPLETED" }
#     #         ]
#     #     }


#     # ── program.load ──
#     if cmd_name == "program.load":
#         steps += [
#             {"type": "EMIT_EVENT", "eventName": "program_load_begin"},
#             {"type": "WAIT_MS", "durationMs": 50},
#             {"type": "EMIT_EVENT", "eventName": "program_load_done"},
#         ]

#     # ── startup.sequence ──
#     if cmd_name == "startup.sequence":
#         steps += [
#             {"type": "EMIT_EVENT", "eventName": "hw_init_start"},
#             {"type": "WAIT_MS", "durationMs": 1000},
#             {"type": "EMIT_EVENT", "eventName": "hw_init_done"},
#         ]

#     # ── pot.fill_start ──
#     # Firmware opens paint_inlet and holds it open.
#     # Edge hub sends pot.fill_stop when target weight reached.
#     if cmd_name == "pot.fill_start":
#         steps += [
#             {"type": "OPEN_VALVE", "valve": "paint_inlet"},
#             {"type": "EMIT_EVENT", "eventName": "pot_fill_started"},
#             # Firmware stays here — no auto-close. Edge hub sends fill_stop.
#             {"type": "WAIT_FOR_CMD", "waitCmd": "pot.fill_stop"},
#         ]

#     # ── pot.fill_stop ──
#     if cmd_name == "pot.fill_stop":
#         steps += [
#             {"type": "CLOSE_VALVE", "valve": "paint_inlet"},
#             {"type": "EMIT_EVENT", "eventName": "pot_fill_stopped"},
#         ]

#     # ── pot.pressurise ──
#     # Time-based: open pot_air_in for open_ms then close.
#     if cmd_name == "pot.pressurise":
#         open_ms = payload.get("open_ms", 12000)
#         steps += [
#             {"type": "OPEN_VALVE", "valve": "pot_air_in"},
#             {"type": "EMIT_EVENT", "eventName": "pressurise_start"},
#             {"type": "WAIT_MS", "durationMs": open_ms},
#             {"type": "CLOSE_VALVE", "valve": "pot_air_in"},
#             {"type": "EMIT_EVENT", "eventName": "pressurise_done"},
#         ]

#     # ── pot.depressurise ──
#     if cmd_name == "pot.depressurise":
#         steps += [
#             {"type": "OPEN_VALVE", "valve": "pot_air_out"},
#             {"type": "WAIT_MS", "durationMs": 3000},
#             {"type": "CLOSE_VALVE", "valve": "pot_air_out"},
#             {"type": "EMIT_EVENT", "eventName": "depressurise_done"},
#         ]

#     # ── line.prime_start ──
#     # Opens dispense valve and holds.
#     # Edge hub sends line.prime_stop when prime detected.
#     if cmd_name == "line.prime_start":
#         timeout_ms = payload.get("timeout_ms", 180000)
#         steps += [
#             {"type": "OPEN_VALVE", "valve": "dispense"},
#             {"type": "EMIT_EVENT", "eventName": "line_prime_started"},
#             {"type": "WAIT_FOR_CMD", "waitCmd": "line.prime_stop",
#                 "timeoutMs": timeout_ms},
#         ]

#     # ── line.prime_stop ──
#     if cmd_name == "line.prime_stop":
#         steps += [
#             {"type": "CLOSE_VALVE", "valve": "dispense"},
#             {"type": "EMIT_EVENT", "eventName": "line_prime_stopped"},
#         ]

#     # ── dispense.open ──
#     # Open for exactly open_ms then close automatically.
#     if cmd_name == "dispense.open":
#         open_ms = payload.get("open_ms", 400)
#         steps += [
#             {"type": "OPEN_VALVE", "valve": "dispense"},
#             {"type": "WAIT_MS", "durationMs": open_ms},
#             {"type": "CLOSE_VALVE", "valve": "dispense"},
#             {"type": "EMIT_EVENT", "eventName": "dispense_complete"},
#         ]

#     # ── dispense.stop ──
#     # Emergency close — used on pass exit if dispense.open is still running
#     if cmd_name == "dispense.stop":
#         steps += [
#             {"type": "CLOSE_VALVE", "valve": "dispense"},
#             {"type": "EMIT_EVENT", "eventName": "dispense_stopped"},
#         ]

#     # ── program.stop ──
#     if cmd_name == "program.stop":
#         steps += [
#             {"type": "CLOSE_VALVE", "valve": "dispense"},
#             {"type": "CLOSE_VALVE", "valve": "paint_inlet"},
#             {"type": "CLOSE_VALVE", "valve": "pot_air_in"},
#             {"type": "EMIT_EVENT", "eventName": "program_stopped"},
#         ]

#     # ── system.emergency_stop ──
#     if cmd_name == "system.emergency_stop":
#         steps += [
#             {"type": "CLOSE_ALL_VALVES"},
#             {"type": "EMIT_EVENT", "eventName": "emergency_stop"},
#         ]
    
#     if cmd_name == "demo.run":
#             valves = DEVICE_MAP["valves"]
#             refill_time = int(payload.get("refill_ms", 3000))
#             prime_time = int(payload.get("prime_ms", 4000))
            
#             steps = []
#             steps.append({ "type": "CMD_ACK_RECEIVED" })
#             steps.append({ "type": "CMD_ACK_STARTED" })

#             # --- PHASE 1: CREATE PRESSURE DIFFERENTIAL ---
#             # Vent the Pot and Pressurize the Reservoir simultaneously
#             steps.append({"type": "EMIT_EVENT", "eventName": "prep_differential_start"})
#             steps.append({"type": "OPEN_VALVE", "valveId": valves["pot_air_out"]}) # 
#             steps.append({"type": "WAIT_MS", "durationMs": 2000}) 
#             steps.append({"type": "CLOSE_VALVE", "valveId": valves["pot_air_out"]})
#             steps.append({"type": "WAIT_MS", "durationMs": 1000}) 

#             steps.append({"type": "OPEN_VALVE", "valveId": valves["res_air_in"]})  # Valve 5
#             steps.append({"type": "WAIT_MS", "durationMs": 4000}) 
#             steps.append({"type": "CLOSE_VALVE", "valveId": valves["res_air_in"]})
#             steps.append({"type": "WAIT_MS", "durationMs": 1000}) 

#             # --- PHASE 2: PRESSURE-ASSISTED REFILL ---
#             # Open the paint line while maintaining the differential
#             steps.append({"type": "EMIT_EVENT", "eventName": "refill_active"})
#             steps.append({"type": "OPEN_VALVE", "valveId": valves["paint_inlet"]}) # Valve 2
#             steps.append({"type": "WAIT_MS", "durationMs": refill_time})
#             steps.append({"type": "CLOSE_VALVE", "valveId": valves["paint_inlet"]})
#             steps.append({"type": "WAIT_MS", "durationMs": 1000}) 

#             # Close the paint line FIRST, then stop the air
#             # steps.append({"type": "CLOSE_VALVE", "valveId": valves["pot_air_out"]})

#             # --- PHASE 3: PRIME THE POT FOR WORK ---
#             # Now that it's full, bring the pot up to working pressure
#             steps.append({"type": "EMIT_EVENT", "eventName": "pot_priming"})
#             steps.append({"type": "OPEN_VALVE", "valveId": valves["pot_air_in"]})  # Valve 3
#             steps.append({"type": "WAIT_MS", "durationMs": prime_time})
#             steps.append({"type": "CLOSE_VALVE", "valveId": valves["pot_air_in"]})
#             steps.append({"type": "WAIT_MS", "durationMs": 1000}) 


#        # Open the paint line while maintaining the differential
#             steps.append({"type": "EMIT_EVENT", "eventName": "dispense_active"})
#             steps.append({"type": "OPEN_VALVE", "valveId": valves["dispense"]}) # Valve 2
#             steps.append({"type": "WAIT_MS", "durationMs": 1400})
#             steps.append({"type": "CLOSE_VALVE", "valveId": valves["dispense"]})
#             steps.append({"type": "WAIT_MS", "durationMs": 1000}) 


#             # --- PHASE 4: SAFE THE RESERVOIR ---
#             # Vent the remaining pressure from the reservoir
#             steps.append({"type": "OPEN_VALVE", "valveId": valves["res_air_out"]}) # Valve 6
#             steps.append({"type": "WAIT_MS", "durationMs": 1000})
#             steps.append({"type": "CLOSE_VALVE", "valveId": valves["res_air_out"]})
#             steps.append({"type": "WAIT_MS", "durationMs": 1000}) 



#             steps.append({"type": "EMIT_EVENT", "eventName": "machine_ready_state"})
#             steps.append({ "type": "CMD_ACK_COMPLETED" })

#             return {
#                 # "workflow_id": str(uuid.uuid4()),
#                 "name": "pressure_assisted_prep",
#                 "cmd_id": cmd_id,
#                 "steps": steps
#             }

#     # FALLBACK
#     # return {
#     #     "name": "noop",
#     #     "cmd_id": cmd_id,
#     #     "steps": []
#     # }
#     return None

