import json
import os
from app.state.material_state import material_state_manager

STATE_FILE = "/var/lib/edge/material_state.json"

def save_material_state():
    with open(STATE_FILE, "w") as f:
        json.dump(material_state_manager.state.__dict__, f)

def load_material_state():
    if not os.path.exists(STATE_FILE):
        return
    with open(STATE_FILE) as f:
        data = json.load(f)
    material_state_manager.state.__dict__.update(data)
