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
        "pot_air_in": 2,
        "pot_air_out": 3,
        "vclean": 4,
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


        # ------------------------------------------------
        # PHASE 2 — PRIME POT FOR OPERATION
        # ------------------------------------------------
        {"type": "EMIT_EVENT", "eventName": "pot_priming"},
        {"type": "OPEN_VALVE", "valveId": valves["pot_air_in"]},
        {"type": "WAIT_MS", "durationMs": prime_time},
        {"type": "CLOSE_VALVE", "valveId": valves["pot_air_in"]},
        {"type": "WAIT_MS", "durationMs": 1000},

        # ------------------------------------------------
        # PHASE 3 — DISPENSE TEST SHOT
        # ------------------------------------------------
        {"type": "EMIT_EVENT", "eventName": "dispense_active"},
        {"type": "OPEN_VALVE", "valveId": valves["dispense"]},
        {"type": "WAIT_MS", "durationMs": 1400},
        {"type": "CLOSE_VALVE", "valveId": valves["dispense"]},
        {"type": "WAIT_MS", "durationMs": 1000},


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

    # elif cmd_name == "pot.fill_start":
    #     steps += [
    #         {"type": "OPEN_VALVE", "valveId": DEVICE_MAP["valves"]["paint_inlet"]},
    #         {"type": "EMIT_EVENT", "eventName": "pot_fill_started"},
    #     ]


    # elif cmd_name == "pot.fill_stop":
    #     steps += [
    #         {"type": "CLOSE_VALVE", "valveId": DEVICE_MAP["valves"]["paint_inlet"]},
    #         {"type": "EMIT_EVENT", "eventName": "pot_fill_stopped"},
    #     ]

    # elif cmd_name == "pot.pressurise":
    #     open_ms = payload.get("open_ms", 12000)
    #     steps += [
    #         {"type": "OPEN_VALVE", "valveId": DEVICE_MAP["valves"]["pot_air_in"]},
    #         {"type": "EMIT_EVENT", "eventName": "pressurise_start"},
    #         {"type": "WAIT_MS", "durationMs": open_ms},
    #         {"type": "CLOSE_VALVE", "valveId": DEVICE_MAP["valves"]["pot_air_in"]},
    #         {"type": "EMIT_EVENT", "eventName": "pressurise_done"},
    #     ]

    # elif cmd_name == "pot.pressurise":
    #     steps += [
    #         {"type": "OPEN_VALVE", "valveId": DEVICE_MAP["valves"]["pot_air_in"]},
    #         {"type": "EMIT_EVENT", "eventName": "pressurise_started"},
    #     ]
        

    # elif cmd_name == "system.clean":

    #     cycles = int(payload.get("cycles", 3))
    #     flush_ms = int(payload.get("flush_ms", 15000))

    #     for i in range(cycles):
    #         steps += [
    #             {"type": "EMIT_EVENT", "eventName": f"clean_cycle_{i}"},

    #             # 1. depressurise pot
    #             {"type": "OPEN_VALVE", "valveId": DEVICE_MAP["valves"]["pot_air_out"]},
    #             {"type": "WAIT_MS", "durationMs": 20000},
    #             {"type": "CLOSE_VALVE", "valveId": DEVICE_MAP["valves"]["pot_air_out"]},

    #             # 2. flush cleaning liquid
    #             {"type": "OPEN_VALVE", "valveId": DEVICE_MAP["valves"]["vclean"]},
    #             {"type": "WAIT_MS", "durationMs": flush_ms},
    #             {"type": "CLOSE_VALVE", "valveId": DEVICE_MAP["valves"]["vclean"]},

    #                           # 1. depressurise pot
    #             {"type": "OPEN_VALVE", "valveId": DEVICE_MAP["valves"]["pot_air_in"]},
    #             {"type": "WAIT_MS", "durationMs": 5000},
    #             {"type": "CLOSE_VALVE", "valveId": DEVICE_MAP["valves"]["pot_air_in"]},


    #             # 3. purge through nozzle
    #             {"type": "OPEN_VALVE", "valveId": DEVICE_MAP["valves"]["dispense"]},
    #             {"type": "WAIT_MS", "durationMs": 500},
    #             {"type": "CLOSE_VALVE", "valveId": DEVICE_MAP["valves"]["dispense"]},

    #                        # 3. purge through nozzle
    #             {"type": "OPEN_VALVE", "valveId": DEVICE_MAP["valves"]["dispense"]},
    #             {"type": "WAIT_MS", "durationMs": 200},
    #             {"type": "CLOSE_VALVE", "valveId": DEVICE_MAP["valves"]["dispense"]},

    #                        # 3. purge through nozzle
    #             {"type": "OPEN_VALVE", "valveId": DEVICE_MAP["valves"]["dispense"]},
    #             {"type": "WAIT_MS", "durationMs": 400},
    #             {"type": "CLOSE_VALVE", "valveId": DEVICE_MAP["valves"]["dispense"]},

    #                        # 3. purge through nozzle
    #             {"type": "OPEN_VALVE", "valveId": DEVICE_MAP["valves"]["dispense"]},
    #             {"type": "WAIT_MS", "durationMs": 1500},
    #             {"type": "CLOSE_VALVE", "valveId": DEVICE_MAP["valves"]["dispense"]},

    #                        # 3. purge through nozzle
    #             {"type": "OPEN_VALVE", "valveId": DEVICE_MAP["valves"]["dispense"]},
    #             {"type": "WAIT_MS", "durationMs": 10000},
    #             {"type": "CLOSE_VALVE", "valveId": DEVICE_MAP["valves"]["dispense"]},
    #         ]


    elif cmd_name == "system.clean":
        cycles = int(payload.get("cycles", 1))   # always 1 per workflow call
        flush_ms = int(payload.get("flush_ms", 45000))
        flush_ms = min(flush_ms, 55000)  # hard cap under firmware timeout

        steps += [
            {"type": "EMIT_EVENT", "eventName": "clean_cycle_start"},

            {"type": "OPEN_VALVE",  "valveId": DEVICE_MAP["valves"]["pot_air_out"]},
            {"type": "WAIT_MS",     "durationMs": 5000},
            {"type": "CLOSE_VALVE", "valveId": DEVICE_MAP["valves"]["pot_air_out"]},

            {"type": "OPEN_VALVE",  "valveId": DEVICE_MAP["valves"]["vclean"]},
            {"type": "WAIT_MS",     "durationMs": flush_ms},
            {"type": "CLOSE_VALVE", "valveId": DEVICE_MAP["valves"]["vclean"]},

            {"type": "OPEN_VALVE",  "valveId": DEVICE_MAP["valves"]["pot_air_in"]},
            {"type": "WAIT_MS",     "durationMs": 3000},
            {"type": "CLOSE_VALVE", "valveId": DEVICE_MAP["valves"]["pot_air_in"]},

            {"type": "OPEN_VALVE",  "valveId": DEVICE_MAP["valves"]["dispense"]},
            {"type": "WAIT_MS",     "durationMs": 3000},
            {"type": "CLOSE_VALVE", "valveId": DEVICE_MAP["valves"]["dispense"]},

            {"type": "EMIT_EVENT",  "eventName": "clean_cycle_done"},
        ]


    # elif cmd_name == "pot.pressurise":
    #     open_ms = payload.get("open_ms", 8000)

    #     steps += [
    #         {"type": "OPEN_VALVE", "valveId": DEVICE_MAP["valves"]["pot_air_in"]},
    #         {"type": "WAIT_MS", "durationMs": open_ms},
    #         {"type": "CLOSE_VALVE", "valveId": DEVICE_MAP["valves"]["pot_air_in"]},
    #         {"type": "EMIT_EVENT", "eventName": "pressurise_done"},
    #     ]

    elif cmd_name == "pot.pressurise":
        steps += [
            {"type": "OPEN_VALVE", "valveId": DEVICE_MAP["valves"]["pot_air_in"]},
            {"type": "EMIT_EVENT", "eventName": "pressurise_started"},
        ]



    elif cmd_name == "pot.pressurise_stop":
        steps += [
            {"type": "CLOSE_VALVE", "valveId": DEVICE_MAP["valves"]["pot_air_in"]},
            {"type": "EMIT_EVENT", "eventName": "pressurise_stopped"},
        ]

    elif cmd_name == "pot.depressurise":
        steps += [
            {"type": "OPEN_VALVE", "valveId": DEVICE_MAP["valves"]["pot_air_out"]},
            {"type": "WAIT_MS", "durationMs": 5000},
            {"type": "CLOSE_VALVE", "valveId": DEVICE_MAP["valves"]["pot_air_out"]},
            {"type": "EMIT_EVENT", "eventName": "depressurise_done"},
        ]

    elif cmd_name == "pot.vent_open":
        # Opens pot_air_out and holds — no auto-close.
        # mid_refill_orchestrator sends pot.vent_close when fill is done.
        steps += [
            {"type": "OPEN_VALVE", "valveId": DEVICE_MAP["valves"]["pot_air_out"]},
            {"type": "EMIT_EVENT", "eventName": "pot_vent_opened"},
        ]

    elif cmd_name == "pot.vent_close":
        # Closes pot_air_out after fill is complete.
        steps += [
            {"type": "CLOSE_VALVE", "valveId": DEVICE_MAP["valves"]["pot_air_out"]},
            {"type": "EMIT_EVENT", "eventName": "pot_vent_closed"},
        ]

    elif cmd_name == "dispense.open":
        open_ms = payload.get("open_ms", 1000)
        steps += [
            {"type": "OPEN_VALVE", "valveId": DEVICE_MAP["valves"]["dispense"]},
            {"type": "WAIT_MS", "durationMs": open_ms},
            {"type": "CLOSE_VALVE", "valveId": DEVICE_MAP["valves"]["dispense"]},
            {"type": "EMIT_EVENT", "eventName": "dispense_complete"},
        ]

    elif cmd_name == "dispense.start":
        steps += [
            {"type": "OPEN_VALVE", "valveId": DEVICE_MAP["valves"]["dispense"]},
            {"type": "EMIT_EVENT", "eventName": "dispense_started"},
        ]

    elif cmd_name == "dispense.stop":
        steps += [
            {"type": "CLOSE_VALVE", "valveId": DEVICE_MAP["valves"]["dispense"]},
            {"type": "EMIT_EVENT", "eventName": "dispense_stopped"},
        ]

    # elif cmd_name == "dispense.stop":
    #     steps += [
    #         {"type": "CLOSE_VALVE", "valveId": DEVICE_MAP["valves"]["dispense"]},
    #         {"type": "EMIT_EVENT", "eventName": "dispense_stopped"},
    #     ]
    
    # elif cmd_name == "res.pressurise":
    #     open_ms = payload.get("open_ms", 4000)
    #     steps += [
    #         {"type": "OPEN_VALVE", "valveId": DEVICE_MAP["valves"]["res_air_in"]},
    #         {"type": "EMIT_EVENT", "eventName": "res_pressurise_start"},
    #         {"type": "WAIT_MS", "durationMs": open_ms},
    #         {"type": "CLOSE_VALVE", "valveId": DEVICE_MAP["valves"]["res_air_in"]},
    #         {"type": "EMIT_EVENT", "eventName": "res_pressurise_done"},
    #     ]

    # elif cmd_name == "res.depressurise":
    #     steps += [
    #         {"type": "OPEN_VALVE", "valveId": DEVICE_MAP["valves"]["res_air_out"]},
    #         {"type": "WAIT_MS", "durationMs": 2000},
    #         {"type": "CLOSE_VALVE", "valveId": DEVICE_MAP["valves"]["res_air_out"]},
    #         {"type": "EMIT_EVENT", "eventName": "res_depressurise_done"},
    #     ]


    elif cmd_name == "program.stop":
        open_ms = payload.get("open_ms", 60000)
        steps += [
            {"type": "CLOSE_VALVE", "valveId": DEVICE_MAP["valves"]["dispense"]},
            {"type": "CLOSE_VALVE", "valveId": DEVICE_MAP["valves"]["pot_air_in"]},
            {"type": "OPEN_VALVE", "valveId": DEVICE_MAP["valves"]["pot_air_out"]},
            {"type": "WAIT_MS", "durationMs": open_ms},
            {"type": "CLOSE_VALVE", "valveId": DEVICE_MAP["valves"]["pot_air_out"]},

            {"type": "OPEN_VALVE", "valveId": DEVICE_MAP["valves"]["pot_air_out"]},
            {"type": "WAIT_MS", "durationMs": open_ms},
            {"type": "CLOSE_VALVE", "valveId": DEVICE_MAP["valves"]["pot_air_out"]},

            {"type": "OPEN_VALVE", "valveId": DEVICE_MAP["valves"]["pot_air_out"]},
            {"type": "WAIT_MS", "durationMs": open_ms},
            {"type": "CLOSE_VALVE", "valveId": DEVICE_MAP["valves"]["pot_air_out"]},

            {"type": "OPEN_VALVE", "valveId": DEVICE_MAP["valves"]["pot_air_out"]},
            {"type": "WAIT_MS", "durationMs": open_ms},
            {"type": "CLOSE_VALVE", "valveId": DEVICE_MAP["valves"]["pot_air_out"]},

            {"type": "EMIT_EVENT", "eventName": "program_stopped"},
        ]

    elif cmd_name == "system.emergency_stop":
        steps += [
            {"type": "CLOSE_ALL_VALVES"},
            {"type": "EMIT_EVENT", "eventName": "emergency_stop"},
        ]


    # elif cmd_name == "nozzle.open":
    #     steps += [
    #         {"type": "OPEN_VALVE", "valveId": DEVICE_MAP["valves"]["nozzle"]},
    #         {"type": "EMIT_EVENT", "eventName": "nozzle_opened"},
    #     ]

    # elif cmd_name == "nozzle.close":
    #     steps += [
    #         {"type": "CLOSE_VALVE", "valveId": DEVICE_MAP["valves"]["nozzle"]},
    #         {"type": "EMIT_EVENT", "eventName": "nozzle_closed"},
    #     ]


    elif cmd_name == "demo.run":
        return _build_demo_workflow(payload, cmd_id)
    
    # elif cmd_name == "line.prime_start":
    #     steps += [
    #         {"type": "OPEN_VALVE", "valveId": DEVICE_MAP["valves"]["dispense"]},
    #         {"type": "EMIT_EVENT", "eventName": "line_prime_started"},
    #     ]

    elif cmd_name == "line.prime_start":
        steps += [
            {"type": "OPEN_VALVE", "valveId": DEVICE_MAP["valves"]["dispense"]},

            # # open nozzle for purge
            # {"type": "OPEN_VALVE", "valveId": DEVICE_MAP["valves"]["nozzle"]},

            {"type": "WAIT_MS", "durationMs": 2000},

            # close nozzle but keep dispense open
            # {"type": "CLOSE_VALVE", "valveId": DEVICE_MAP["valves"]["nozzle"]},

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


