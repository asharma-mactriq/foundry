# app/api/modes.py

from fastapi import APIRouter
from app.modes.mode_manager import mode_manager
from app.modes.mode_types import (
    OperationMode, ProcessMode,
    PressureMode, VisionMode, FaultMode
)

router = APIRouter()

@router.get("/")
def get_modes():
    return mode_manager.get()

@router.post("/operation/{mode}")
def set_op(mode: OperationMode):
    mode_manager.set_operation(mode)
    return mode_manager.get()

@router.post("/process/{mode}")
def set_proc(mode: ProcessMode):
    mode_manager.set_process(mode)
    return mode_manager.get()

@router.post("/pressure/{mode}")
def set_pressure(mode: PressureMode):
    mode_manager.set_pressure(mode)
    return mode_manager.get()

@router.post("/vision/{mode}")
def set_vision(mode: VisionMode):
    mode_manager.set_vision(mode)
    return mode_manager.get()

@router.post("/fault/{mode}")
def set_fault(mode: FaultMode):
    mode_manager.set_fault(mode)
    return mode_manager.get()
