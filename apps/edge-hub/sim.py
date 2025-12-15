import time, json, requests, random

while True:
    data = {
        "flow": random.randint(10, 40),
        "gap": random.choice([0, 1]),
        "ts": time.time()
    }

    requests.post("http://localhost:5001/telemetry/", json=data)
    print("Sent →", data)

    time.sleep(0.01)
