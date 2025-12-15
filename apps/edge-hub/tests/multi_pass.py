import time
import json
import random
import paho.mqtt.client as mqtt

HOST = "127.0.0.1"
PORT = 1883
TOPIC = "machine/1/status"

client = mqtt.Client()
client.connect(HOST, PORT, 60)
client.loop_start()

def send(gap, flow=None, pressure=None):
    payload = {
        "gap": gap,
        "flow": flow if flow is not None else random.randint(10, 40),
        "pressure": pressure if pressure is not None else round(random.uniform(1.0, 2.2), 2)
    }
    print(">>>", payload)
    client.publish(TOPIC, json.dumps(payload))

def simulate_pass(pass_id):
    print(f"\n=== PASS {pass_id} START ===")

    # -------------------------
    # ENTER (0 → 1)
    # -------------------------
    send(gap=1)
    time.sleep(random.uniform(0.05, 0.2))

    # -------------------------
    # STABLE WINDOW (gap=1 longer)
    # -------------------------
    time.sleep(0.3)
    send(gap=1)

    # -------------------------
    # SPRAYING (flow spikes)
    # -------------------------
    for _ in range(random.randint(2, 5)):
        send(gap=1, flow=random.randint(30, 45))
        time.sleep(random.uniform(0.1, 0.25))

    # -------------------------
    # EXIT (1 → 0)
    # -------------------------
    send(gap=0)
    time.sleep(random.uniform(0.2, 0.4))

    print(f"=== PASS {pass_id} END ===\n")

print("\n######## MULTI-PASS TEST ########\n")
time.sleep(1)

NUM_PASSES = 10   # change this anytime

for p in range(1, NUM_PASSES + 1):
    simulate_pass(p)

print("######## TEST DONE ########\n")
time.sleep(1)
