from fastapi import APIRouter
from fastapi import Request

# from app.program.program_engine import program_engine
from app.state.program_state import program_state
from app.state.machine_state import machine_state_manager
from app.core import clock

router = APIRouter()


@router.post("/start")
def start_program(request: Request):

    program_engine = request.app.state.program_engine

    st = machine_state_manager.state
    st.gap_prev = 0
    st.gap = 0
    st.gap_transition = None
    st.plate_stable = False
    st.plate_stable_since = clock.mono()

    config = {
        "program_id": "default",
        "total_passes": 50,
        "passes": {}
    }

    program_engine.start_program(config)

    return {"ok": True}


@router.post("/stop")
def stop_program(request: Request):
    from app.modes.mode_manager import mode_manager
    from app.modes.mode_types import OperationMode, ProcessMode
    
    program_engine = request.app.state.program_engine
    program_engine.stop_program()

     # Reset modes so next program.load is allowed
    mode_manager.set_operation(OperationMode.manual)
    mode_manager.set_process(ProcessMode.idle)

    return {"ok": True}



@router.get("/state")
def get_program_state():
    return program_state.serialize()


# # app/api/program.py
# from fastapi import APIRouter
# from app.state.program_state import program_state
# from app.state.machine_state import machine_state_manager
# import time

# router = APIRouter()

# @router.post("/start")
# def start_program():
#     # Ensure next incoming telemetry will produce a clean 0 -> 1 enter transition.
#     # Only reset gap-related fields to avoid stomping other machine state.
#     st = machine_state_manager.state
#     st.gap_prev = 0
#     st.gap = 0
#     st.gap_transition = None
#     st.plate_stable = False
#     st.plate_stable_since = time.time()

#     # Start program (thread-safe)
#     program_state.start_program()

#     return {"ok": True}

# @router.post("/stop")
# def stop_program():
#     program_state.stop_program()
#     return {"ok": True}

# @router.get("/state")
# def get_program_state():
#     return program_state.serialize()

