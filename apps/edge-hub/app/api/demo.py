from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter(prefix="/api/demo", tags=["demo"])


class DemoRunRequest(BaseModel):
    runs: int = 3


@router.post("/run")
def run_demo(req: DemoRunRequest, request: Request):
    executor = request.app.state.executor

    if executor is None:
        raise RuntimeError("Executor not initialized")

    cmd_id = executor.send_command({
        "name": "demo.run",
        "payload": {
            "runs": req.runs
        },
        "execution": "bootstrap"
    })

    return {
        "ok": True,
        "cmd_id": cmd_id,
        "mode": "bootstrap",
        "runs": req.runs
    }
