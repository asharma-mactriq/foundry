# app/api/telemetry.py

import time
from fastapi import APIRouter
from app.services.telemetry_service import telemetry_service

router = APIRouter()

@router.post("/")
async def ingest(data: dict):
    enriched = {
        "deviceId": "edge1",
        "ts_edge": time.time(),
        **data
    }

    telemetry_service.update(enriched)
    return {"status": "ok"}
