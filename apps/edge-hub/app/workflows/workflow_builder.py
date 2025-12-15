# app/workflows/workflow_builder.py
#
# Converts high-level Edge commands (pressure.reprime, purge.nozzle, refill.start)
# into low-level Workflow JSON for the runtime.
#

from typing import Dict, Any


# ----------------------------------------------------------------------
# Device map (TEMP VERSION)
# You should move this to app/device_config/device_map.py later.
# ----------------------------------------------------------------------
DEVICE_MAP = {
    "valves": {
        "dispense": 1,
        "refill": 2,
        "purge": 3,
        "pressurize": 4
    },
    "sensors": {
        "pressure": 1,
        "flow": 1
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
        valve = DEVICE_MAP["valves"]["pressurize"]
        return {
            "name": "pressure_reprime",
            "cmd_id": cmd_id,
            "steps": [
                { "type": "CMD_ACK_RECEIVED" },
                { "type": "CMD_ACK_STARTED" }, 
                {"type": "OPEN_VALVE", "valveId": valve},
                {"type": "WAIT_MS", "durationMs": payload.get("duration_ms", 5000)},
                {"type": "CHECK_PRESSURE", "threshold": payload.get("threshold", 1.5)},
                {"type": "CLOSE_VALVE", "valveId": valve},
                {"type": "EMIT_EVENT", "eventName": "reprime_done"},
                { "type": "CMD_ACK_COMPLETED" }

            ]
        }

    # REFILL START
    if cmd_name == "refill.start":
        valve = DEVICE_MAP["valves"]["refill"]
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
        valve = DEVICE_MAP["valves"]["purge"]
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
                # Valve 1
                {"type": "OPEN_VALVE", "valveId": 1},
                {"type": "WAIT_MS", "durationMs": 5000},
                {"type": "CLOSE_VALVE", "valveId": 1},
                {"type": "WAIT_MS", "durationMs": 200},

                # Valve 2
                {"type": "OPEN_VALVE", "valveId": 2},
                {"type": "WAIT_MS", "durationMs": 2000},
                {"type": "CLOSE_VALVE", "valveId": 2},
                {"type": "WAIT_MS", "durationMs": 200},

                # Valve 3
                {"type": "OPEN_VALVE", "valveId": 3},
                {"type": "WAIT_MS", "durationMs": 2000},
                {"type": "CLOSE_VALVE", "valveId": 3},
                {"type": "WAIT_MS", "durationMs": 200},

                # Valve 4
                {"type": "OPEN_VALVE", "valveId": 4},
                {"type": "WAIT_MS", "durationMs": 2000},
                {"type": "CLOSE_VALVE", "valveId": 4},
                {"type": "WAIT_MS", "durationMs": 200},

                # Valve 5
                {"type": "OPEN_VALVE", "valveId": 5},
                {"type": "WAIT_MS", "durationMs": 2000},
                {"type": "CLOSE_VALVE", "valveId": 5},
                {"type": "WAIT_MS", "durationMs": 200},
            ]
        }


    # FALLBACK
    return {
        "name": "noop",
        "cmd_id": cmd_id,
        "steps": []
    }
