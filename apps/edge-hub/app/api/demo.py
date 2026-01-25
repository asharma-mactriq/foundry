from fastapi import APIRouter
from pydantic import BaseModel

from app.services.command_executor import executor

router = APIRouter(prefix="/api/demo", tags=["demo"])


class DemoRunRequest(BaseModel):
    runs: int = 3


@router.post("/run")
def run_demo(req: DemoRunRequest):
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
