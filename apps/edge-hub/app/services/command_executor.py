# app/services/command_executor.py

import uuid
import time
import json
import threading
import requests

from app.commands.command_queue import command_queue
from app.services.command_store import command_store
from app.services.device_state import device_state
from app.workflows.workflow_builder import build_workflow_for_command

from app.state.machine_state import machine_state_manager, MachinePhase
from app.state.program_state import program_state
from app.modes.mode_manager import mode_manager
from app.modes.mode_types import FaultMode



class CommandExecutor:
    def __init__(self, mqtt_client, tick_ms=50):
        self.client = mqtt_client
        self.running = False
        self.tick = tick_ms / 1000.0

        # currently active command waiting for ACK
        self.current_cmd = None
        self.sent_at = None

    def start(self):
        self.running = True
        threading.Thread(target=self.loop, daemon=True).start()
        print("[EXECUTOR] Started")

    def loop(self):
        while self.running:
            time.sleep(self.tick)

            # if waiting for ACK, check timeout
            if self.current_cmd:
                self._check_timeout()
                continue

            # fetch next command from queue
            cmd = command_queue.pop_valid()
            if cmd:
                self._send(cmd)

    def _guard_command(self, cmd: dict) -> bool:
        """
        Final safety gate before sending command to ESP32.
        Guard decides IF command is allowed — not HOW it executes.
        """
        name = cmd.get("name", "")

        # Only guard physical actuation commands
        if not name.startswith(("dispense", "pressure", "refill")):
            return True

        ms = machine_state_manager.state
        ps = program_state
        modes = mode_manager.get()

        # -------- GLOBAL SAFETY --------
        if modes["fault"] != FaultMode.none:
            print(f"[GUARD] Blocked {name}: fault={modes['fault']}")
            return False

        if not ps.running:
            print(f"[GUARD] Blocked {name}: program not running")
            return False

        # -------- DISPENSE-SPECIFIC --------
        if name.startswith("dispense"):
            if ms.phase != MachinePhase.REST_DISPENSE_EDGE:
                print(f"[GUARD] Blocked {name}: phase={ms.phase}")
                return False

        return True


    # def _send(self, cmd):
    #     self.current_cmd = cmd
    #     self.sent_at = time.time()

    #     command_store.update_status(cmd["cmd_id"], "sent", {"sent_at": self.sent_at})

    #     print(f"[EXECUTOR → DEVICE] {cmd['cmd_id']} | {cmd['name']}")

    #     self.client.publish("devices/edge1/commands", json.dumps(cmd))

    # def _send(self, cmd):
    #     # 1. Handle LOCAL commands first
    #     if self._handle_local_command(cmd):
    #         command_store.update_status(cmd["cmd_id"], "acked", {"local": True})
    #         self.current_cmd = None
    #         self.sent_at = None
    #         return

    #     # 2. Otherwise → send over MQTT
    #     self.current_cmd = cmd
    #     self.sent_at = time.time()

    #     command_store.update_status(cmd["cmd_id"], "sent", {"sent_at": self.sent_at})

    #     print(f"[EXECUTOR → DEVICE] {cmd['cmd_id']} | {cmd['name']}")
    #     self.client.publish("devices/edge1/commands", json.dumps(cmd))

    def _send(self, cmd):

    # 0. GUARD — FINAL SAFETY GATE
        if not self._guard_command(cmd):
            command_store.update_status(
                cmd["cmd_id"],
                "blocked",
                {"reason": "guard_reject"}
            )
            print(f"[EXECUTOR] Command blocked by guard: {cmd['name']}")
            return



        # 1. Handle local commands
        if self._handle_local_command(cmd):
            command_store.update_status(cmd["cmd_id"], "acked", {"local": True})
            self.current_cmd = None
            self.sent_at = None
            return

        # 2. Convert to workflow
        from app.workflows.workflow_builder import build_workflow_for_command
        wf = build_workflow_for_command(cmd["name"], cmd["payload"], cmd["cmd_id"])
        json_wf = json.dumps(wf)

        # 3. Set active command
        self.current_cmd = cmd
        self.sent_at = time.time()
        command_store.update_status(cmd["cmd_id"], "sent", {"sent_at": self.sent_at})

        print(f"[EXECUTOR → DEVICE] {cmd['cmd_id']} | {cmd['name']}")
        print(f"[EXECUTOR → DEVICE] sending workflow: {json_wf}")

        # 4. Publish to correct topic
        self.client.publish("devices/edge1/workflow/start", json_wf)



    def ack_received(self, cmd_id, *args, **kwargs):
        if not self.current_cmd:
            return

        if cmd_id != self.current_cmd["cmd_id"]:
            print("[EXECUTOR] Ignoring mismatched ACK")
            return

        print(f"[EXECUTOR] ACK received for {cmd_id}")

        # update local db
        command_store.update_status(cmd_id, "acked")
        device_state.update_ack(cmd_id)

        # ⭐⭐⭐ FORWARD TO NEXTJS BACKEND ⭐⭐⭐
        try:
            requests.post(
                "http://localhost:3001/command-acks",
                json={"cmd_id": cmd_id, "status": "acked"},
                timeout=0.3
            )
            print("[EXECUTOR] Forwarded ACK to backend")
        except Exception as e:
            print("[EXECUTOR] Failed to forward ACK:", e)

        # clear active command
        self.current_cmd = None
        self.sent_at = None


    def _check_timeout(self):
        elapsed = time.time() - self.sent_at
        timeout_s = 1.0  # 1000 ms

        if elapsed > timeout_s:
            cmd_id = self.current_cmd["cmd_id"]
            print(f"[EXECUTOR] TIMEOUT for {cmd_id}")

            command_store.update_status(cmd_id, "timeout", {"elapsed": elapsed})

            self.current_cmd = None
            self.sent_at = None
    
    def send_command(self, cmd: dict):
        """
        Public API used by RuleEngine, WorkflowEngine, ProgramEngine.
        Adds command to queue with a unique cmd_id and lets loop() send it.
        """
        cmd_id = str(uuid.uuid4())
        now = time.time() # FIX: Need current time for DB fields
        
        # 1. Add required fields for CommandExecutor and CommandStore schema
        cmd["cmd_id"] = cmd_id
        cmd["name"] = cmd.get("name") or cmd.get("cmd") or "unnamed"
        
        # FIX: ADD MISSING DB SCHEMA FIELDS HERE
        cmd["deviceId"] = cmd.get("deviceId", "edge1") # Default device ID
        cmd["type"] = cmd.get("cmd") # Use the 'cmd' field as the 'type' for the DB
        cmd["payload"] = cmd.get("payload", {"valve_id": cmd.get("valve_id")}) # Move details to payload
        cmd["priority"] = cmd.get("priority", 10)
        cmd["issued_at"] = cmd.get("issued_at", now)
        cmd["valid_until"] = cmd.get("valid_until", now + 60) # Default 60s validity
        cmd["status"] = cmd.get("status", "queued")

        # 2. Push into queue
        command_queue.push(cmd)

        # 3. Store in DB
        command_store.add(cmd) 

        print(f"[EXECUTOR] Queued command {cmd_id} → {cmd}")
        return cmd_id

    def enqueue_command(self, cmd):
        from app.commands.command_queue import command_queue
        command_queue.push(cmd)
    
    def _handle_local_command(self, cmd):
        name = cmd.get("name")
        payload = cmd.get("payload", {})

        # ---------------------------------------------
        # LOCAL MODE CHANGE HANDLER
        # ---------------------------------------------
        if name == "system.set_mode":
            from app.modes.mode_manager import mode_manager, OperationMode

            mode_str = payload.get("mode")
            if not mode_str:
                print("[EXECUTOR] system.set_mode missing payload.mode")
                return True

            try:
                new_mode = OperationMode(mode_str)
            except Exception:
                print(f"[EXECUTOR] invalid operation mode '{mode_str}'")
                return True

            mode_manager.set_operation(new_mode)
            print(f"[EXECUTOR] Operation mode changed → {new_mode}")

            return True  # stops MQTT send

        return False

    def workflow_complete_received(self, workflow_name, cmd_id):
        if not self.current_cmd:
            print("[EXECUTOR] Workflow complete but no command active")
            return

        if self.current_cmd["cmd_id"] != cmd_id:
            print("[EXECUTOR] Workflow complete for wrong command!")
            return

        print(f"[EXECUTOR] Workflow complete for {cmd_id}")

        command_store.update_status(cmd_id, "acked", {"workflow": workflow_name})
        device_state.update_ack(cmd_id)

        self.current_cmd = None
        self.sent_at = None

    def step_ack_received(self, data):
        cmd_id = data["commandId"]
        step_index = data["stepIndex"]
        step_type = data["stepType"]
        success = data.get("success", True)

        # Reset timeout
        self.sent_at = time.time()

        # Persist to DB
        command_store.add_step(
            cmd_id=cmd_id,
            step_index=step_index,
            step_type=step_type,
            event="step",
            success=success
        )

        print(f"[EXECUTOR] STEP → cmd={cmd_id}, idx={step_index}, type={step_type}, success={success}")



executor = None
