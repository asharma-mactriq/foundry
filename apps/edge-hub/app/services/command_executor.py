# app/services/command_executor.py
import uuid
import time
import json
import threading
import requests
from app.core import clock

from app.commands.command_queue import command_queue
from app.services.command_store import command_store
from app.services.device_state import device_state

from app.state.machine_state import machine_state_manager, MachinePhase
from app.state.program_state import program_state
from app.state.program_state import ProgramPhase
from app.modes.mode_manager import mode_manager
from app.modes.mode_types import FaultMode

from app.state.material_state import material_state_manager
from app.commands.command_registry import command_registry

from app.state.system_state import system_state, SystemPhase


MIN_USABLE_KG = 0.3  # or whatever your real safety threshold is

class CommandExecutor:
    def __init__(self, mqtt_client, tick_ms=50):
        self.client = mqtt_client
        self.running = False
        self.tick = tick_ms / 1000.0
        # self.interrupt_map = {
        #     "pot.fill_start": "pot.fill_stop",
        #     "line.prime_start": "line.prime_stop",
        # }

        # currently active command waiting for ACK
        self.current_cmd = None
        self.sent_at = None

    def start(self):
        self.running = True
        threading.Thread(target=self.loop, daemon=True).start()
        print("[EXECUTOR] Started")

    def is_busy(self) -> bool:
        return self.current_cmd is not None

    def loop(self):
        while self.running:
            time.sleep(self.tick)

            # if waiting for ACK, check timeout
            if self.current_cmd:
                self._check_timeout()
                continue

            # if self.current_cmd:
            #     self._check_timeout()

            #     # Allow interrupt commands to pass through
            #     next_cmd = command_queue.peek_valid()  # you must add this method

            #     if next_cmd:
            #         active_name = self.current_cmd.get("name")
            #         incoming_name = next_cmd.get("name")
            #         expected_interrupt = self.interrupt_map.get(active_name)

            #         if incoming_name == expected_interrupt:
            #             cmd = command_queue.pop_valid()
            #             try:
            #                 self._send_interrupt(cmd)
            #             except Exception as e:
            #                 print("[EXECUTOR CRASH]", e)

            #     continue

            # fetch next command from queue
            cmd = command_queue.pop_valid()
            if cmd:
                try:
                    self._send(cmd)
                except Exception as e:
                    print("[EXECUTOR CRASH]", e)
                    import traceback
                    traceback.print_exc()


    # def lifecycle_ack_received(self, data):
    #         """
    #         Processes command lifecycle events (received, started, completed).
    #         'command.completed' is the trigger to unlock the queue.
    #         """

    #         print(f"[EXECUTOR] Lifecycle event: {event} for {cmd_id}")

    #         cmd_id = data.get("commandId") or data.get("cmd_id")
    #         event = data.get("event")

    #         # 1. Validation: Only process if it matches our active command
    #         if not self.current_cmd or self.current_cmd["cmd_id"] != cmd_id:
    #             return

            
    #         if cmd is None or cmd.get("cmd_id") != cmd_id:
    #             print(f"[EXECUTOR] WARNING: completed ACK for unknown cmd {cmd_id}")
    #             return
            
    #         cmd_name = self.current_cmd.get("name")

    #         # Stop the Scheduler from resending the command once the device acknowledges it
    #         if event == "command.received":
    #             command_store.update_status(cmd_id, "acked", data)
                
    #         elif event == "command.started":
    #             command_store.update_status(cmd_id, "started", data)

    #             from app.program.program_engine import program_engine

    #             if program_engine:
    #                 cmd_name = self.current_cmd.get("name")

    #                 if cmd_name == "refill.start":
    #                     program_engine.refill_state = "RUNNING"
    #                     print("[EXECUTOR] Refill workflow running")

                    

    #         # ---------------------------

    #         # 2. Release Lock: If completed, allow the next command to be popped from queue
    #         if event == "command.completed":
    #             # print(f"[EXECUTOR] SUCCESS: Release lock for {cmd_id}")
    #             # Mark as completed in DB so history is accurate
    #             command_store.update_status(cmd_id, "completed", data)

    #             from app.program.program_engine import program_engine

    #             if program_engine:
    #                 cmd_name = self.current_cmd.get("name")

    #                 # -------------------------------------
    #                 # REFILL LIFECYCLE HANDLING
    #                 # -------------------------------------
    #                 if cmd_name == "refill.start":
    #                     program_engine.refill_state = "IDLE"
    #                     print("[EXECUTOR] Refill workflow completed → state reset")

    #             from app.state.program_state import program_state

    #             if cmd_name == "program.load":
    #                 program_state.on_loaded()

    #                 from app.program.program_engine import program_engine
    #                 from app.state.machine_state import machine_state_manager

    #                 if program_engine:
    #                     program_engine.on_event(
    #                         machine_state_manager.state,
    #                         program_state
    #                     )

    #             elif cmd_name == "startup.sequence":
    #                 program_state.on_startup_complete()

    #             elif cmd_name == "program.stop":
    #                 program_state.stop_program()

    #             print(f"[EXECUTOR] SUCCESS: Release lock for {cmd_id}")
    
    #             self.current_cmd = None
    #             self.sent_at = None
    #         # # 2. Release Lock: If completed, allow the next command to be popped from queue
    #         # if event == "command.completed":
    #         #     print(f"[EXECUTOR] SUCCESS: Release lock for {cmd_id}")
    #         #     self.current_cmd = None
    #         #     self.sent_at = None


    def lifecycle_ack_received(self, data: dict):
        """
        Processes command lifecycle events (received, started, completed).
        'command.completed' is the trigger to unlock the queue.
        """

        cmd_id = data.get("commandId") or data.get("cmd_id")
        event = data.get("event")

        print(f"[EXECUTOR] Lifecycle event: {event} for {cmd_id}")

        # 1️⃣ Validate active command
        if not self.current_cmd:
            return

        if self.current_cmd.get("cmd_id") != cmd_id:
            print(f"[EXECUTOR] WARNING: ACK for unknown cmd {cmd_id}")
            return

        cmd_name = self.current_cmd.get("name")

        # 2️⃣ Intermediate states
        if event == "command.received":
            command_store.update_status(cmd_id, "acked", data)
            return

        if event == "command.started":
            command_store.update_status(cmd_id, "started", data)

            from app.program.program_engine import program_engine
            if program_engine and cmd_name == "refill.start":
                program_engine.refill_state = "RUNNING"
                print("[EXECUTOR] Refill workflow running")

            return

        # 3️⃣ Completion unlock
        if event != "command.completed":
            return

        command_store.update_status(cmd_id, "completed", data)

        from app.program.program_engine import program_engine

        if program_engine and cmd_name == "refill.start":
            program_engine.refill_state = "IDLE"
            print("[EXECUTOR] Refill workflow completed → state reset")

        if cmd_name == "program.load":
            program_state.on_loaded()
              # 👇 TRIGGER STARTUP
            self.send_command({
                "name": "startup.sequence",
                "payload": {}
            })

        

        elif cmd_name == "startup.sequence":
            program_state.begin_startup()

            from app.modes.mode_types import OperationMode
            mode_manager.set_operation(OperationMode.auto)


            from app.orchestrators.startup_orchestrator import startup_orchestrator
            profile = program_engine.profile
            startup_orchestrator.begin(profile=profile)



            # self.send_command({
            #     "name": "pot.fill_start",
            #     "payload": {"target_kg": profile.pot_fill_target_kg}
            # })



        elif cmd_name == "program.stop":
            program_state.stop_program()

        print(f"[EXECUTOR] SUCCESS: Release lock for {cmd_id}")

        self.current_cmd = None
        self.sent_at = None

    def _guard_command(self, cmd: dict) -> bool:

        BOOTSTRAP_COMMANDS = {
            "pressure.reprime",
            "pressure.release",
            "refill.start",
            "system.reset",
            "pot.fill_start",
            "pot.fill_stop",
            "pot.pressurise",
            "pot.depressurise",
            "line.prime_start",
            "line.prime_stop",
        }


        # BOOTSTRAP_COMMANDS = {
        #     "pressure.reprime",
        #     "pressure.release",
        #     "refill.start",
        #     "system.reset",
        # }

        """
        Final safety gate before sending command to ESP32.
        Guard decides IF command is allowed — not HOW it executes.
        """

        name = cmd.get("name", "")

                # --------------------------------------------------
        # BOOTSTRAP / COMMISSIONING EXECUTION MODE
        # Allows limited commands to run without telemetry
        # --------------------------------------------------
        execution = cmd.get("execution", "normal")

        BOOTSTRAP_ALLOWED = {
            "demo.run",
            "program.start",
            "pressure.reprime",
            "refill.start",
        }

        if execution == "bootstrap":
            if name in BOOTSTRAP_ALLOWED:
                print(f"[GUARD BYPASS] bootstrap execution for {name}")
                return True
            else:
                return block("bootstrap_not_allowed")


        ms = machine_state_manager.state
        ps = program_state
        mat = material_state_manager.state
        modes = mode_manager.get()

        def block(reason):
            print(f"\n[GUARD BLOCKED]")
            print(f"  cmd        : {name}")
            print(f"  reason     : {reason}")
            print(f"  phase      : {ms.phase}")
            print(f"  pressure   : {ms.pressure}")
            print(f"  pot_ml     : {mat.current_pot_kg}")
            # print(f"  program    : running={ps.running}")
            print(f"  program    : phase={ps.phase}")

            print(f"  fault      : {modes['fault']}\n")

            if self.client:
                payload = {
                    "cmd": name,
                    "reason": reason,
                    "phase": str(ms.phase),
                    "system": system_state.phase.value,
                    # "mode": modes["current"],
                    "mode": modes.get("operation"),
                    "pressure": ms.pressure,
                    "pot_volume_ml": mat.current_pot_kg,
                    # "program_running": ps.running,
                    "program_phase": ps.phase.value,
                    "fault": modes["fault"],
                }
                self.client.publish("edge/guards", json.dumps(payload))

            return False

        # --------------------------------------------------
        # GLOBAL SYSTEM READINESS (MUST BE FIRST)
        # --------------------------------------------------
        if system_state.phase != SystemPhase.READY:
            # Allow bootstrap commands to MAKE the system ready
            if name not in BOOTSTRAP_COMMANDS:
                if name.startswith(("dispense", "refill", "pressure")):
                    return block("system_not_ready")


        # Only guard physical actuation commands
        if not name.startswith(("dispense", "pressure", "refill")):
            return True

        # --------------------------------------------------
        # FAULT MODE
        # --------------------------------------------------
        if modes["fault"] != FaultMode.none:
            return block(f"fault={modes['fault']}")

        # --------------------------------------------------
        # PROGRAM STATE
        # --------------------------------------------------
        # if not ps.running:
        #     return block("program not running")
        if ps.phase not in (
            ProgramPhase.STARTUP,
            ProgramPhase.READY,
            ProgramPhase.RUNNING,
            ProgramPhase.LOADED
        ):
            return block(f"program_phase_invalid:{ps.phase}")

        # --------------------------------------------------
        # MATERIAL SAFETY
        # --------------------------------------------------
        if name.startswith("dispense"):
            # if not mat.line_primed:
            #     return block("dispense line not primed")

            # if mat.current_pot_kg <= MIN_USABLE_KG:
            #     return block("insufficient paint in pot")
            
            pass

        # --------------------------------------------------
        # MACHINE PHASE
        # --------------------------------------------------
        if name.startswith("dispense"):
            if name == "dispense.stop":
                pass  # always allow stop — safety command, no phase restriction
            if ms.phase != MachinePhase.REST_DISPENSE_EDGE:
                return block(f"invalid phase {ms.phase}")

        print(f"[GUARD ALLOWED] {name}")
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
        name = cmd.get("name", "")
        execution = cmd.get("execution", "normal")

        BOOTSTRAP_ALLOWED = {
            "demo.run",
            "program.start",
            "pressure.reprime",
            "refill.start",
        }

        if execution == "bootstrap" and name in BOOTSTRAP_ALLOWED:
            print(f"[EXECUTOR] Bootstrap bypass for {name}")
            return self._send_without_mode_policy(cmd)

        return self._send_with_mode_policy(cmd)


    def _send_with_mode_policy(self, cmd):
        # ---------- MODE / POLICY VALIDATION ----------
        try:
            spec = command_registry.get(cmd["name"])
            mode_state = mode_manager.get()

            if not spec.is_allowed_in_mode(mode_state):
                command_store.update_status(
                    cmd["cmd_id"],
                    "blocked",
                    {"reason": "mode_not_allowed"}
                )
                print(f"[EXECUTOR] Blocked by mode policy: {cmd['name']}")
                return

        except KeyError:
            command_store.update_status(
                cmd["cmd_id"],
                "blocked",
                {"reason": "unknown_command"}
            )
            print(f"[EXECUTOR] Unknown command: {cmd['name']}")
            return

        return self._send_common(cmd)

    
    def _send_without_mode_policy(self, cmd):
        # Skip registry mode enforcement entirely
        return self._send_common(cmd)


    def _send_common(self, cmd):

        name = cmd.get("name", "")

        # 0. GUARD — FINAL SAFETY GATE
        if not self._guard_command(cmd):
            command_store.update_status(
                cmd["cmd_id"],
                "blocked",
                {"reason": "guard_reject"}
            )
            print(f"[EXECUTOR] Command blocked by guard: {cmd['name']}")
            return
        
        # --------------------------------------------------
    # WAIT_FOR_CMD EVENTS (DO NOT BUILD WORKFLOW)
    # --------------------------------------------------
        # if name in ("pot.fill_stop", "line.prime_stop"):

        #     self.current_cmd = cmd
        #     self.sent_at = clock.mono()

        #     command_store.update_status(
        #         cmd["cmd_id"],
        #         "sent",
        #         {"sent_at": self.sent_at}
        #     )

        #     print(f"[EXECUTOR → DEVICE] EVENT {cmd['cmd_id']} | {name}")

        #     self.client.publish(
        #         "devices/edge1/commands",
        #         json.dumps({
        #             "command": name,
        #             "cmd_id": cmd["cmd_id"]
        #         })
        #     )

        #     return


        if cmd["name"] == "dispense.open":
            ms = machine_state_manager.state
            if getattr(ms, "dispense_fired_for_gap", False):
                command_store.update_status(
                    cmd["cmd_id"],
                    "blocked",
                    {"reason": "already_dispensed_for_gap"}
                )
                print("[EXECUTOR] dispense already fired for this gap — blocked")
                return

            # mark as fired (one-shot)
            ms.dispense_fired_for_gap = True

        # 1. Handle local commands
        if self._handle_local_command(cmd):
            command_store.update_status(cmd["cmd_id"], "acked", {"local": True})
            self.current_cmd = None
            self.sent_at = None
            return

        # 2. Convert to workflow
        from app.workflows.workflow_builder import build_workflow_for_command
        # wf = build_workflow_for_command(cmd["name"], cmd["payload"], cmd["cmd_id"])
        # json_wf = json.dumps(wf)

        wf = build_workflow_for_command(cmd["name"], cmd["payload"], cmd["cmd_id"])

        if not wf:
            print(f"[EXECUTOR] Workflow ignored (idempotent): {cmd['name']}")
            command_store.update_status(
                cmd["cmd_id"],
                "ignored",
                {"reason": "idempotent_noop"}
            )
            return

        json_wf = json.dumps(wf)


        # 3. Set active command
        self.current_cmd = cmd
        self.sent_at = clock.mono()
        command_store.update_status(cmd["cmd_id"], "sent", {"sent_at": self.sent_at})

        print(f"[EXECUTOR → DEVICE] {cmd['cmd_id']} | {cmd['name']}")
        print(f"[EXECUTOR → DEVICE] sending workflow: {json_wf}")

        # 4. Publish to correct topic
        self.client.publish("devices/edge1/workflow/start", json_wf)


    # def _send_interrupt(self, cmd):
    #     from app.workflows.workflow_builder import build_workflow_for_command

    #     wf = build_workflow_for_command(
    #         cmd["name"],
    #         cmd["payload"],
    #         cmd["cmd_id"]
    #     )

    #     if not wf:
    #         command_store.update_status(
    #             cmd["cmd_id"],
    #             "ignored",
    #             {"reason": "idempotent_noop"}
    #         )
    #         return

    #     json_wf = json.dumps(wf)

    #     command_store.update_status(
    #         cmd["cmd_id"],
    #         "sent",
    #         {"sent_at": clock.mono()}
    #     )

    #     print(f"[EXECUTOR → DEVICE] INTERRUPT {cmd['cmd_id']} | {cmd['name']}")
    #     self.client.publish("devices/edge1/workflow/start", json_wf)

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
        # self.current_cmd = None
        # self.sent_at = None


    def _check_timeout(self):
            if not self.current_cmd:
                return

            elapsed = clock.mono() - self.sent_at

            # workflow, it might have crashed. We release the lock
            # so the next command in the queue can try to run.
            if elapsed > 60.0: 
                cmd_id = self.current_cmd["cmd_id"]
                print(f"[EXECUTOR] TIMEOUT for {cmd_id} - Releasing Lock")
                
                command_store.update_status(cmd_id, "timeout", {"elapsed": elapsed})

                self.current_cmd = None # <--- THIS IS KEY
                self.sent_at = None
                
    # def _check_timeout(self):
    #     elapsed = time.time() - self.sent_at
    #     timeout_s = 5.0  # 15 seconds

        

    #     if elapsed > timeout_s:
    #         cmd_id = self.current_cmd["cmd_id"]
    #         print(f"[EXECUTOR] TIMEOUT for {cmd_id}")

    #         command_store.update_status(cmd_id, "timeout", {"elapsed": elapsed})

    #         self.current_cmd = None
    #         self.sent_at = None
    
    def send_command(self, cmd: dict):
        """
        Public API used by RuleEngine, WorkflowEngine, ProgramEngine.
        Adds command to queue with a unique cmd_id and lets loop() send it.
        """
        cmd_id = str(uuid.uuid4())
        now = time.time() # FIX: Need current time for DB fields
        # now_wall = clock.wall_ts()
        # now_mono = clock.mono()

        
        # 1. Add required fields for CommandExecutor and CommandStore schema
        cmd["cmd_id"] = cmd_id
        cmd["name"] = cmd.get("name") or cmd.get("cmd") or "unnamed"

        # Preserve execution context (normal | bootstrap)
        cmd["execution"] = cmd.get("execution", "normal")

        
        # FIX: ADD MISSING DB SCHEMA FIELDS HERE
        cmd["deviceId"] = cmd.get("deviceId", "edge1") # Default device ID
        cmd["type"] = cmd.get("cmd") # Use the 'cmd' field as the 'type' for the DB
        cmd["payload"] = cmd.get("payload", {"valve_id": cmd.get("valve_id")}) # Move details to payload
        cmd["priority"] = cmd.get("priority", 10)
        cmd["issued_at"] = cmd.get("issued_at", now)
        cmd["valid_until"] = cmd.get("valid_until", now + 60) # Default 60s validity
        # cmd["issued_at"] = cmd.get("issued_at", now_wall.isoformat())
        # cmd["valid_until"] = cmd.get("valid_until", clock.wall_ts().isoformat())

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

        # self.current_cmd = None
        # self.sent_at = None

    def step_ack_received(self, data):
        cmd_id = data["commandId"]
        step_index = data["stepIndex"]
        step_type = data["stepType"]
        success = data.get("success", True)

        # Reset timeout
        self.sent_at = clock.mono()

        # Persist to DB
        command_store.add_step(
            cmd_id=cmd_id,
            step_index=step_index,
            step_type=step_type,
            event="step",
            success=success
        )

        print(f"[EXECUTOR] STEP → cmd={cmd_id}, idx={step_index}, type={step_type}, success={success}")



# executor = None
