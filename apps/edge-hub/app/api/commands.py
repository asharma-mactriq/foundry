# app/api/commands.py
from fastapi import APIRouter, HTTPException, Request
from app.services.command_store import command_store

router = APIRouter()


# -----------------------------------------------------------
# NEW DISPATCH ONLY (NO OLD CODE)
# -----------------------------------------------------------
# @router.post("/dispatch")
# def dispatch(body: dict, request: Request):
#     try:
#         dispatcher = request.app.state.dispatcher
#         if dispatcher is None:
#             raise RuntimeError("Dispatcher not initialized")

#         name = body["name"]          # required
#         payload = body.get("payload", {})

#         cmd = dispatcher.dispatch(name=name, payload=payload)

#         return {"status": "queued", "cmd_id": cmd["cmd_id"]}

#     except Exception as e:
#         raise HTTPException(status_code=400, detail=str(e))

@router.post("/dispatch")
def dispatch(body: dict, request: Request):
    try:
        dispatcher = request.app.state.dispatcher
        if dispatcher is None:
            raise RuntimeError("Dispatcher not initialized")

        name = body["name"]
        payload = body.get("payload", {})

        # Route system.clean through orchestrator
        if name == "system.clean":
            from app.orchestrators.clean_orchestrator import clean_orchestrator
            cycles = payload.get("cycles", 1)
            flush_ms = payload.get("flush_ms", 45000)
            clean_orchestrator.start(cycles=cycles, flush_ms=flush_ms)
            return {"status": "queued", "cycles": cycles, "flush_ms": flush_ms}

        cmd = dispatcher.dispatch(name=name, payload=payload)
        return {"status": "queued", "cmd_id": cmd["cmd_id"]}

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# -----------------------------------------------------------
# COMMAND STATUS
# -----------------------------------------------------------
@router.get("/status/{cmd_id}")
def get_status(cmd_id: str):
    cmd = command_store.get(cmd_id)
    if not cmd:
        raise HTTPException(status_code=404, detail="Command not found")
    return cmd
