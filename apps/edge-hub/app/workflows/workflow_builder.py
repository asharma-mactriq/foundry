# app/workflows/workflow_builder.py
#
# Converts high-level Edge commands (pressure.reprime, purge.nozzle, refill.start)
# into low-level Workflow JSON for the runtime.
#
import uuid  # <--- Add this line
import json
# ... other imports
from typing import Dict, Any


# ----------------------------------------------------------------------
# Device map (TEMP VERSION)
# You should move this to app/device_config/device_map.py later.
# ----------------------------------------------------------------------
# DEVICE_MAP = {
#     "valves": {
#         "dispense": 1,
#         "refill": 2,
#         "purge": 3,
#         "pressurize": 4
#     },
#     "sensors": {
#         "pressure": 1,
#         "flow": 1
#     }
# }
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



# ----------------------------------------------------------------------
# MAIN ENTRY POINT
# ----------------------------------------------------------------------
def build_workflow_for_command(cmd_name: str, payload: Dict[str, Any], cmd_id: str) -> Dict[str, Any]:
    """
    Convert a high-level command into a runtime workflow JSON object.
    """

    if cmd_name == "program.load":
        return {
        "name": "program_load",
        "cmd_id": cmd_id,
        "steps": [
            { "type": "CMD_ACK_RECEIVED" },
            { "type": "CMD_ACK_STARTED" },
            {"type": "EMIT_EVENT", "eventName": "program_load_begin"},
            {"type": "WAIT_MS", "durationMs": 50},
            {"type": "EMIT_EVENT", "eventName": "program_load_done"},
            { "type": "CMD_ACK_COMPLETED" }

        ]
    }

    # if cmd_name == "program.start":
    #     return {
    #         "name": "program_start",
    #         "cmd_id": cmd_id,
    #         "steps": [
    #             { "type": "CMD_ACK_RECEIVED" },
    #             { "type": "CMD_ACK_STARTED" },
    #             {"type": "EMIT_EVENT", "eventName": "program_start_begin"},
    #             {"type": "WAIT_MS", "durationMs": 5000},
    #             {"type": "EMIT_EVENT", "eventName": "program_start_done"},
    #             { "type": "CMD_ACK_COMPLETED" }

    #         ]
    # }

    if cmd_name == "dispense.start":
        return {
            "name": "dispense_start",
            "cmd_id": cmd_id,
            "steps": [
                { "type": "CMD_ACK_RECEIVED" },
                { "type": "CMD_ACK_STARTED" },
                { "type": "OPEN_VALVE", "valveId": 1 },
                { "type": "WAIT_MS", "durationMs": 120 },
                { "type": "CLOSE_VALVE", "valveId": 1 },
                { "type": "CMD_ACK_COMPLETED" }
            ]
        }

    if cmd_name == "program.stop":
        return {
            "name": "program_stop",
            "cmd_id": cmd_id,
            "steps": [
                { "type": "CMD_ACK_RECEIVED" },
                { "type": "CMD_ACK_STARTED" },
                {"type": "EMIT_EVENT", "eventName": "program_stop_begin"},
                {"type": "WAIT_MS", "durationMs": 50},
                {"type": "EMIT_EVENT", "eventName": "program_stop_done"},
                { "type": "CMD_ACK_COMPLETED" }
            ]
    }

    if cmd_name == "program.next_pass":
        return {
            "name": "program_next_pass",
            "cmd_id": cmd_id,
            "steps": [
                { "type": "CMD_ACK_RECEIVED" },
                { "type": "CMD_ACK_STARTED" }, 
                {"type": "EMIT_EVENT", "eventName": "program_next_pass_begin"},
                {"type": "WAIT_MS", "durationMs": 50},
                {"type": "EMIT_EVENT", "eventName": "program_next_pass_done"},
                { "type": "CMD_ACK_COMPLETED" }
            ]
        }



    # PRESSURE REPRIME
    if cmd_name == "pressure.reprime":
        valve = DEVICE_MAP["valves"]["pot_air_in"]
        return {
            "name": "pressure_reprime",
            "cmd_id": cmd_id,
            "steps": [
                { "type": "CMD_ACK_RECEIVED" },
                { "type": "CMD_ACK_STARTED" },
                { "type": "OPEN_VALVE", "valveId": valve },
                { "type": "WAIT_MS", "durationMs": payload.get("duration_ms", 5000) },
                # { "type": "CHECK_PRESSURE", "threshold": payload.get("threshold", 1.5) },
                { "type": "CLOSE_VALVE", "valveId": valve },
                { "type": "EMIT_EVENT", "eventName": "reprime_done" },
                { "type": "CMD_ACK_COMPLETED" }
            ]
        }

    # REFILL START
    if cmd_name == "refill.start":
        valve = DEVICE_MAP["valves"]["paint_inlet"]
        return {
            "name": "refill_cycle",
            "cmd_id": cmd_id,
            "steps": [
                { "type": "CMD_ACK_RECEIVED" },
                { "type": "CMD_ACK_STARTED" }, 
                {"type": "OPEN_VALVE", "valveId": valve},
                {"type": "WAIT_MS", "durationMs": payload.get("duration_ms", 2000)},
                {"type": "CLOSE_VALVE", "valveId": valve},
                {"type": "EMIT_EVENT", "eventName": "refill_done"},
                { "type": "CMD_ACK_COMPLETED" }

            ]
        }

    # PURGE NOZZLE
    if cmd_name == "purge.nozzle":
        valve = DEVICE_MAP["valves"]["dispense"]
        return {
            "name": "purge_nozzle",
            "cmd_id": cmd_id,
            "steps": [
                { "type": "CMD_ACK_RECEIVED" },
                { "type": "CMD_ACK_STARTED" }, 
                {"type": "OPEN_VALVE", "valveId": valve},
                {"type": "WAIT_MS", "durationMs": payload.get("duration_ms", 1000)},
                {"type": "CLOSE_VALVE", "valveId": valve},
                {"type": "EMIT_EVENT", "eventName": "purge_complete"},
                { "type": "CMD_ACK_COMPLETED" }
            ]
        }

    # MANUAL DISPENSE OPEN
    if cmd_name == "dispense.open":
        dur = payload.get("open_ms", 100)
        return {
            "name": "manual_dispense",
            "cmd_id": cmd_id,
            "steps": [
                { "type": "CMD_ACK_RECEIVED" },
                { "type": "CMD_ACK_STARTED" }, 
                {"type": "OPEN_VALVE", "valveId": DEVICE_MAP["valves"]["dispense"]},
                {"type": "WAIT_MS", "durationMs": dur},
                {"type": "CLOSE_VALVE", "valveId": DEVICE_MAP["valves"]["dispense"]},
                {"type": "EMIT_EVENT", "eventName": "dispense_manual_done"},
                { "type": "CMD_ACK_COMPLETED" }
            ]
        }
    
    if cmd_name == "program.start":
        return {
            "name": "program_start",
            "cmd_id": cmd_id,
            "steps": [
                { "type": "CMD_ACK_RECEIVED" },
                { "type": "CMD_ACK_STARTED" },
                { "type": "EMIT_EVENT", "eventName": "program_started" },
                { "type": "CMD_ACK_COMPLETED" }
            ]
        }
    
        # --------------------------------------------------
    # DEMO RUN (BOOTSTRAP SAFE)
    # --------------------------------------------------
    # --------------------------------------------------
    # DEMO RUN (PARSER-SAFE)
    # --------------------------------------------------

    # if cmd_name == "demo.run":
    #         runs = int(payload.get("runs", 1))
    #         step_dur = int(payload.get("duration_ms", 5000))
    #         steps = []
            
    #         steps.append({ "type": "CMD_ACK_RECEIVED" })
    #         steps.append({ "type": "CMD_ACK_STARTED" })
            
    #         valve_ids = [1, 2, 3, 4, 5, 6]

    #         for _ in range(runs): # Wrap the sequence in the runs loop
    #             for v_id in valve_ids:
    #                 steps.append({ "type": "OPEN_VALVE", "valveId": v_id })
    #                 steps.append({ "type": "WAIT_MS", "durationMs": step_dur })
    #                 steps.append({ "type": "CLOSE_VALVE", "valveId": v_id })
    #                 steps.append({ "type": "WAIT_MS", "durationMs": 500 })

    #         # Safing steps
    #         for v_id in valve_ids:
    #             steps.append({ "type": "CLOSE_VALVE", "valveId": v_id })

    #         steps.append({ "type": "CMD_ACK_COMPLETED" })

    #         # MUST RETURN THE OBJECT HERE
    #         return {
    #             "workflow_id": str(uuid.uuid4()),
    #             "name": "sequential_led_test",
    #             "steps": steps
    #         }

    # up is proper
    if cmd_name == "demo.run":
            valves = DEVICE_MAP["valves"]
            refill_time = int(payload.get("refill_ms", 3000))
            prime_time = int(payload.get("prime_ms", 4000))
            
            steps = []
            steps.append({ "type": "CMD_ACK_RECEIVED" })
            steps.append({ "type": "CMD_ACK_STARTED" })

            # --- PHASE 1: CREATE PRESSURE DIFFERENTIAL ---
            # Vent the Pot and Pressurize the Reservoir simultaneously
            steps.append({"type": "EMIT_EVENT", "eventName": "prep_differential_start"})
            steps.append({"type": "OPEN_VALVE", "valveId": valves["pot_air_out"]}) # Valve 4
            steps.append({"type": "WAIT_MS", "durationMs": 2000}) 
            steps.append({"type": "CLOSE_VALVE", "valveId": valves["pot_air_out"]})
            steps.append({"type": "WAIT_MS", "durationMs": 1000}) 

            steps.append({"type": "OPEN_VALVE", "valveId": valves["res_air_in"]})  # Valve 5
            steps.append({"type": "WAIT_MS", "durationMs": 4000}) 
            steps.append({"type": "CLOSE_VALVE", "valveId": valves["res_air_in"]})
            steps.append({"type": "WAIT_MS", "durationMs": 1000}) 

            # --- PHASE 2: PRESSURE-ASSISTED REFILL ---
            # Open the paint line while maintaining the differential
            steps.append({"type": "EMIT_EVENT", "eventName": "refill_active"})
            steps.append({"type": "OPEN_VALVE", "valveId": valves["paint_inlet"]}) # Valve 2
            steps.append({"type": "WAIT_MS", "durationMs": refill_time})
            steps.append({"type": "CLOSE_VALVE", "valveId": valves["paint_inlet"]})
            steps.append({"type": "WAIT_MS", "durationMs": 1000}) 

            # Close the paint line FIRST, then stop the air
            # steps.append({"type": "CLOSE_VALVE", "valveId": valves["pot_air_out"]})

            # --- PHASE 3: PRIME THE POT FOR WORK ---
            # Now that it's full, bring the pot up to working pressure
            steps.append({"type": "EMIT_EVENT", "eventName": "pot_priming"})
            steps.append({"type": "OPEN_VALVE", "valveId": valves["pot_air_in"]})  # Valve 3
            steps.append({"type": "WAIT_MS", "durationMs": prime_time})
            steps.append({"type": "CLOSE_VALVE", "valveId": valves["pot_air_in"]})
            steps.append({"type": "WAIT_MS", "durationMs": 1000}) 

            # --- PHASE 4: SAFE THE RESERVOIR ---
            # Vent the remaining pressure from the reservoir
            steps.append({"type": "OPEN_VALVE", "valveId": valves["res_air_out"]}) # Valve 6
            steps.append({"type": "WAIT_MS", "durationMs": 1000})
            steps.append({"type": "CLOSE_VALVE", "valveId": valves["res_air_out"]})
            steps.append({"type": "WAIT_MS", "durationMs": 1000}) 

            steps.append({"type": "EMIT_EVENT", "eventName": "machine_ready_state"})
            steps.append({ "type": "CMD_ACK_COMPLETED" })

            return {
                "workflow_id": str(uuid.uuid4()),
                "name": "pressure_assisted_prep",
                "cmd_id": cmd_id,
                "steps": steps
            }

#   working
    # if cmd_name == "demo.run":
    #     runs = int(payload.get("runs", 3))
    #     runs = max(1, min(runs, 5))   # HARD LIMIT (important)

    #     steps = []

    #     # ACK SEQUENCE (MANDATORY)
    #     steps.append({ "type": "CMD_ACK_RECEIVED" })
    #     steps.append({ "type": "CMD_ACK_STARTED" })
    #     steps.append({ "type": "EMIT_EVENT", "eventName": "demo_begin" })

    #     for _ in range(runs):
    #         # PRESSURIZE POT
    #         steps.append({ "type": "OPEN_VALVE", "valveId": DEVICE_MAP["valves"]["pot_air_in"] })
    #         steps.append({ "type": "WAIT_MS", "durationMs": 5000 })
    #         steps.append({ "type": "CLOSE_VALVE", "valveId": DEVICE_MAP["valves"]["pot_air_in"] })

    #         # REFILL PAINT
    #         steps.append({ "type": "OPEN_VALVE", "valveId": DEVICE_MAP["valves"]["paint_inlet"] })
    #         steps.append({ "type": "WAIT_MS", "durationMs": 5000 })
    #         steps.append({ "type": "CLOSE_VALVE", "valveId": DEVICE_MAP["valves"]["paint_inlet"] })

    #         # DISPENSE
    #         steps.append({ "type": "OPEN_VALVE", "valveId": DEVICE_MAP["valves"]["dispense"] })
    #         steps.append({ "type": "WAIT_MS", "durationMs": 5000 })
    #         steps.append({ "type": "CLOSE_VALVE", "valveId": DEVICE_MAP["valves"]["dispense"] })

    #     # COMPLETION (MANDATORY LAST STEP)
    #     steps.append({ "type": "CMD_ACK_COMPLETED" })

    #     return {
    #         "name": "demo_run",
    #         "cmd_id": cmd_id,
    #         "steps": steps
    #     }

    # if cmd_name == "demo.run":
    #     runs = payload.get("runs", 3)

    #     steps = [
    #         { "type": "CMD_ACK_RECEIVED" },
    #         { "type": "CMD_ACK_STARTED" },
    #         { "type": "EMIT_EVENT", "eventName": "demo_begin" },
    #     ]

    #     for i in range(runs):
    #         steps.extend([
    #         { "type": "EMIT_EVENT", "eventName": f"cycle_{i+1}_start" },

    #         # Pressurize pot
    #         { "type": "OPEN_VALVE", "valveId": DEVICE_MAP["valves"]["pot_air_in"] },
    #         { "type": "WAIT_MS", "durationMs": 3000 },
    #         { "type": "CLOSE_VALVE", "valveId": DEVICE_MAP["valves"]["pot_air_in"] },

    #         # Refill paint
    #         { "type": "OPEN_VALVE", "valveId": DEVICE_MAP["valves"]["paint_inlet"] },
    #         { "type": "WAIT_MS", "durationMs": 2000 },
    #         { "type": "CLOSE_VALVE", "valveId": DEVICE_MAP["valves"]["paint_inlet"] },

    #         # Dispense
    #         { "type": "OPEN_VALVE", "valveId": DEVICE_MAP["valves"]["dispense"] },
    #         { "type": "WAIT_MS", "durationMs": 150 },
    #         { "type": "CLOSE_VALVE", "valveId": DEVICE_MAP["valves"]["dispense"] },

    #         { "type": "EMIT_EVENT", "eventName": f"cycle_{i+1}_done" },
    #     ])

    #     steps.append({ "type": "CMD_ACK_COMPLETED" })

    #     return {
    #         "name": "demo_run",
    #         "cmd_id": cmd_id,
    #         "steps": steps
    #     }


    # FALLBACK
    return {
        "name": "noop",
        "cmd_id": cmd_id,
        "steps": []
    }
