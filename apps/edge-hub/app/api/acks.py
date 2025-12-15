from fastapi import APIRouter, Request

router = APIRouter()

@router.post("/acks")
async def receive_ack(body: dict, request: Request):
    """
    Edge-Hub receives ACK from ESP32 → forwards to NestJS backend.
    """
    cmd_id = body.get("cmd_id")
    status = body.get("status", "acked")
    
    print("[EDGE-HUB] Forwarding ACK to backend:", body)

    backend_url = request.app.state.config["BACKEND_ACK_URL"]

    import httpx
    async with httpx.AsyncClient() as client:
        await client.post(backend_url, json=body)

    return {"ok": True}
