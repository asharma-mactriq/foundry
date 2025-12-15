"""
test_program_with_report.py

Usage:
  - Ensure your edge hub is running (uvicorn app.main:app).
  - Ensure mosquitto broker is running at 127.0.0.1:1883.
  - Install dependencies: pip install paho-mqtt requests pandas openpyxl
  - Run: python test_program_with_report.py

What it does:
  1) starts program (HTTP POST /program/start if available; else direct import)
  2) simulates N passes by publishing telemetry to "machine/1/status"
  3) stops program
  4) fetches program state and writes program_report.xlsx
"""

import time
import json
import random
import os

# Optional HTTP control of the program API
try:
    import requests
except Exception:
    requests = None

# MQTT publisher
import paho.mqtt.client as mqtt

# For Excel report
try:
    import pandas as pd
except Exception:
    pd = None

# Config
MQTT_HOST = "127.0.0.1"
MQTT_PORT = 1883
STATUS_TOPIC = "machine/1/status"
PROGRAM_START_URL = "http://127.0.0.1:8000/program/start"
PROGRAM_STOP_URL = "http://127.0.0.1:8000/program/stop"
PROGRAM_STATE_URL = "http://127.0.0.1:8000/program/state"

NUM_PASSES = 8
STABLE_WINDOW_S = 0.25   # seconds (should match stable_window_ms in your edge)
SPRAY_CYCLES_MIN = 2
SPRAY_CYCLES_MAX = 5

# Utility: try HTTP start/stop/state; fallback to direct import
def start_program_via_api_or_direct():
    # try HTTP
    if requests:
        try:
            r = requests.post(PROGRAM_START_URL, timeout=1)
            if r.status_code == 200:
                print("[TEST] Started program via HTTP API")
                return "http"
        except Exception:
            pass

    # fallback: direct import (requires running inside same venv & path)
    try:
        from app.state.program_state import program_state
        program_state.start_program()
        print("[TEST] Started program via direct import")
        return "direct"
    except Exception as e:
        print("[TEST] Failed to start program (http/direct):", e)
        raise

def stop_program_via_api_or_direct():
    if requests:
        try:
            r = requests.post(PROGRAM_STOP_URL, timeout=1)
            if r.status_code == 200:
                print("[TEST] Stopped program via HTTP API")
                return "http"
        except Exception:
            pass

    try:
        from app.state.program_state import program_state
        program_state.stop_program()
        print("[TEST] Stopped program via direct import")
        return "direct"
    except Exception as e:
        print("[TEST] Failed to stop program (http/direct):", e)
        raise

def fetch_program_state():
    # HTTP preferred
    if requests:
        try:
            r = requests.get(PROGRAM_STATE_URL, timeout=1)
            if r.status_code == 200:
                print("[TEST] Fetched program state via HTTP")
                return r.json()
        except Exception:
            pass

    # direct fallback
    try:
        from app.state.program_state import program_state
        print("[TEST] Fetched program state via direct import")
        return program_state.serialize()
    except Exception as e:
        print("[TEST] Failed to fetch program state (http/direct):", e)
        raise

# MQTT helper
def publish_status(client, gap, flow=None, pressure=None):
    payload = {
        "gap": gap,
        "flow": flow if flow is not None else random.randint(10, 40),
        "pressure": pressure if pressure is not None else round(random.uniform(1.0, 2.2), 2),
        "ts": int(time.time())
    }
    client.publish(STATUS_TOPIC, json.dumps(payload))
    print(">>> PUBLISHED", payload)

def simulate_pass(client, pid):
    print(f"\n--- SIMULATING PASS {pid} ---")
    # ensure gap=0 baseline
    publish_status(client, 0)
    time.sleep(random.uniform(0.05, 0.12))

    # ENTER (0 -> 1)
    publish_status(client, 1)
    time.sleep(random.uniform(0.02, 0.08))

    # wait stable window (edge code will mark stable after stable_window_ms)
    time.sleep(STABLE_WINDOW_S)
    publish_status(client, 1)

    # spraying cycles while gap=1
    for _ in range(random.randint(SPRAY_CYCLES_MIN, SPRAY_CYCLES_MAX)):
        publish_status(client, 1, flow=random.randint(30, 45),
                       pressure=round(random.uniform(1.1, 1.6), 2))
        time.sleep(random.uniform(0.08, 0.18))

    # EXIT (1 -> 0)
    publish_status(client, 0, flow=random.randint(8, 25))
    time.sleep(random.uniform(0.08, 0.18))
    print(f"--- PASS {pid} DONE ---\n")

def build_excel_report(program_json, out_path="program_report.xlsx"):
    if pd is None:
        print("[REPORT] pandas not installed. Install with: pip install pandas openpyxl")
        return

    # program_json expected to contain 'passes' dict (serialized)
    passes = program_json.get("passes", {})
    rows = []
    for pid_str, p in passes.items():
        # pid_str may be string or int; normalize
        try:
            pid = int(pid_str)
        except:
            pid = pid_str
        rows.append({
            "pass_id": pid,
            "enter_ts": p.get("enter_ts"),
            "stable_ts": p.get("stable_ts"),
            "exit_ts": p.get("exit_ts"),
            "expected_paint": p.get("expected_paint", 0),
            "actual_paint": p.get("actual_paint", 0),
            "thickness_estimate": p.get("thickness_estimate", 0),
            "status": p.get("status", "")
        })

    if not rows:
        print("[REPORT] No passes recorded in program state. Nothing to write.")
        return

    df = pd.DataFrame(rows).sort_values("pass_id")
    # convert timestamps to readable
    def fmt_ts(ts):
        try:
            return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))
        except Exception:
            return ts
    for col in ("enter_ts", "stable_ts", "exit_ts"):
        if col in df.columns:
            df[col] = df[col].apply(fmt_ts)

    # totals & meta
    meta = {
        "program_start_ts": program_json.get("program_start_ts"),
        "total_expected_paint": program_json.get("total_expected_paint"),
        "total_actual_paint": program_json.get("total_actual_paint"),
        "last_event": program_json.get("last_event"),
    }

    # write to excel with two sheets
    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="passes", index=False)
        meta_df = pd.DataFrame(list(meta.items()), columns=["key", "value"])
        meta_df.to_excel(writer, sheet_name="meta", index=False)

    print(f"[REPORT] Written report to {out_path}")

def main():
    print("=== TEST: start program, simulate passes, stop program, build report ===")

    # 1) Start program
    start_program_via_api_or_direct()

    # 2) MQTT connect
    client = mqtt.Client()
    try:
        client.connect(MQTT_HOST, MQTT_PORT, 60)
    except Exception as e:
        print("[TEST] Failed to connect to MQTT broker:", e)
        return
    client.loop_start()
    time.sleep(0.2)

    # 3) Simulate passes
    for i in range(1, NUM_PASSES + 1):
        simulate_pass(client, i)

    # small settle
    time.sleep(0.2)

    # 4) Stop program
    stop_program_via_api_or_direct()

    # 5) Fetch program state
    program_json = fetch_program_state()
    print("\n=== Program State ===")
    print(json.dumps(program_json, indent=2))

    # 6) Build Excel report
    out_path = os.path.join(os.getcwd(), "program_report.xlsx")
    build_excel_report(program_json, out_path=out_path)

    # 7) cleanup
    client.loop_stop()
    client.disconnect()

    print("\n=== TEST COMPLETE ===")
    if os.path.exists(out_path):
        print("Report path:", out_path)

if __name__ == "__main__":
    main()
