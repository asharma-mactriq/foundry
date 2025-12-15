import time
import json
import random
import paho.mqtt.client as mqtt

BROKER = "localhost"
TOPIC = "devices/edge1/telemetry"

client = mqtt.Client()
client.connect(BROKER, 1883, 60)

print("🚀 Telemetry Simulator V2 started...")
print("Publishing realistic machine telemetry...\n")

# ---------- SIMULATION STATE ----------
current_pass = 1
total_passes = 18
baseline_pressure = 2.2
dispensing = False
stable_window = False
flow = 0.0

def random_noise(level=0.03):
    return (random.random() - 0.5) * level

while True:
    ts = time.time()

    # ----------------------------------------
    # 1. GAP DETECTION SIMULATION
    # ----------------------------------------
    gap_prob = random.random()

    # ~85% chance gap is detected normally
    gap_detected = gap_prob > 0.15

    # ~5% chance false negative
    if random.random() < 0.05:
        gap_detected = False

    # ----------------------------------------
    # 2. STABLE VS UNSTABLE PLATE
    # ----------------------------------------
    if gap_detected:
        stable_window = random.random() > 0.2   # 80% stable, 20% flicker
    else:
        stable_window = False

    # ----------------------------------------
    # 3. DISPENSING LOGIC
    # ----------------------------------------
    if stable_window and gap_detected:
        dispensing = True
        # flow increases, but noisy
        flow = max(0, 24 + random_noise(3)*24)  
    else:
        dispensing = False
        flow = 0

    # ----------------------------------------
    # 4. PRESSURE MODEL
    # ----------------------------------------
    # Pressure drifts realistically
    pressure = baseline_pressure + random_noise(0.2)
    pressure = max(1.5, min(3.0, pressure))

    pressure_ok = pressure > 1.8

    # ----------------------------------------
    # 5. PASS TRANSITION
    # ----------------------------------------
    plate_transition = False

    if random.random() < 0.02:   # 2% chance per update
        plate_transition = True
        current_pass += 1
        if current_pass > total_passes:
            current_pass = 1  # restart cycle

    # ----------------------------------------
    # 6. MACHINE STATE MODEL
    # ----------------------------------------
    if dispensing:
        machine_state = "DISPENSING"
    elif stable_window:
        machine_state = "STABLE"
    else:
        machine_state = "IDLE"

    # ----------------------------------------
    # 7. BUILD FINAL TELEMETRY PAYLOAD
    # ----------------------------------------
    payload = {
        "raw": {
            "flow": round(flow, 2),
            "gap": 1 if gap_detected else 0,
            "pressure": round(pressure, 2),
            "ts": ts
        },
        "machine": {
            "state": machine_state,
            "gap_detected": gap_detected,
            "stable_window": stable_window,
            "plate_transition": plate_transition,
            "current_pass": current_pass,
            "pressure_ok": pressure_ok,
            "warnings": [],
            "errors": [],
            "timestamp": ts
        },
        "program": {
            "running": True,
            "current_pass": current_pass,
            "total_passes": total_passes,
            "target_volume": 12.4,
            "actual_volume": round(random.uniform(12.0, 14.0), 2),
            "override": False,
            "refill_required": False,
            "version": 3
        }
    }

    # ----------------------------------------
    # 8. PUBLISH MQTT TELEMETRY
    # ----------------------------------------
    client.publish(TOPIC, json.dumps(payload))

    print("Published:", payload["raw"], "Pass:", current_pass)

    # 10 Hz (100ms interval)
    time.sleep(0.10)
