from fastapi import APIRouter
from app.state.material_state import material_state_manager
from app.state.machine_state import machine_state_manager
from app.state.program_state import program_state

router = APIRouter()

# ---------------------------------------
# EXISTING STATUS ENDPOINTS (keep them)
# ---------------------------------------

@router.get("/material")
def get_material_state():
    """
    Derived paint / material state
    """
    return material_state_manager.state.__dict__


@router.get("/machine")
def get_machine_state():
    return machine_state_manager.state.__dict__


@router.get("/program")
def get_program_state():
    return program_state.serialize()
