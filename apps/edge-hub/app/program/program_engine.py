# app/program/program_engine.py

from dataclasses import field
import time
import uuid

from app.state.program_state import program_state
from app.services.command_executor import CommandExecutor
from app.services.rule_engine import get_rule_engine
from app.state.program_state import ProgramPhase


class ProgramEngine:
    def __init__(self, executor: CommandExecutor):
        self.executor = executor
        self.rule_engine = get_rule_engine(executor=executor)
        self.config = None  # loaded program config from NestJS
        self.startup_started_at = None
        self.pass_started_at = None

        self.refill_state = "IDLE"   # IDLE | REQUESTED | RUNNING
        self.last_refill_ts = 0
        self.refill_threshold_kg = 0.5   # trigger below this
        self.refill_target_kg = 4.0      # stop expecting above this
        self.refill_cooldown_sec = 5
        self.refill_attempts = 0
        self.max_refill_attempts = 3


    # ---------------------------------------------------------
    # Called by NestJS: /program/start
    # ---------------------------------------------------------
    def start_program(self, config: dict):
        print("[PROGRAM_ENGINE] START PROGRAM")
        self.config = config
        program_state.start_program()
        # 2. Send program.load to firmware
        self.executor.send_command({
            "name": "program.load",
            "payload": {
                "program_id": config.get("program_id", "default")
            }
        })

    # ---------------------------------------------------------
    # Called by NestJS: /program/stop
    # ---------------------------------------------------------
    def stop_program(self):
        print("[PROGRAM_ENGINE] STOP PROGRAM")
        self.executor.send_command({
            "name": "program.stop",
            "payload": {}
        })
        program_state.stop_program()

    # ---------------------------------------------------------
    # Called on every new telemetry event AFTER state_orchestrator
    # ---------------------------------------------------------
    # def on_event(self, machine, program):
    #     # if not program.is_running():
    #     #     return

    #     if program.phase not in (
    #         ProgramPhase.READY,
    #         ProgramPhase.RUNNING
    #     ):
    #         return

    #     # event can be None / enter / stable / exit
    #     event = program.last_event

    #     if event == "pass_enter":
    #         self._handle_pass_enter(program)
    #     elif event == "pass_stable":
    #         self._handle_pass_stable(program, machine)
    #     elif event == "pass_exit":
    #         self._handle_pass_exit(program)

    def on_event(self, machine, program):

        # --------------------------------------------------
        # PHASE TRANSITIONS FROM FIRMWARE EVENTS
        # --------------------------------------------------

        if program.phase == ProgramPhase.STARTED:
            # waiting firmware load ack
            return

        # if program.phase == ProgramPhase.LOADED:
        #     program.begin_startup()
        #     self.executor.send_command({
        #         "name": "startup.sequence",
        #         "payload": {}
        #     })
        #     return
        if program.phase == ProgramPhase.LOADED:
            program.begin_startup()

            # if program.phase == ProgramPhase.STARTUP:
            #     self.executor.send_command({
            #         "name": "startup.sequence",
            #         "payload": {}
            #     })

            return

        if program.phase == ProgramPhase.STARTUP:
            self._handle_startup(machine)
            return

        # --------------------------------------------------
        # NORMAL PASS LOGIC
        # --------------------------------------------------

        if program.phase not in (
            ProgramPhase.READY,
            ProgramPhase.RUNNING
        ):
            return
        
        # if program.last_event == "refill_started":
        #     self.refill_state = "RUNNING"

        if program.last_event == "refill_done":
            self.refill_state = "IDLE"
            self.last_refill_ts = time.time()


        if program.phase == ProgramPhase.RUNNING:
            self._maybe_trigger_refill(machine)

        event = program.last_event

        if event == "pass_enter":
            self._handle_pass_enter(program)

        elif event == "pass_stable":
            self._handle_pass_stable(program, machine)

        elif event == "pass_exit":
            self._handle_pass_exit(program)
        
        program.last_event = None


    # ---------------------------------------------------------
    def _handle_pass_enter(self, program):
        pid = program.current_pass
        print(f"[PROGRAM_ENGINE] PASS {pid} ENTER")
        # your logic: nothing needed yet

    # ---------------------------------------------------------
    # When plate is stable → BEGIN DISPENSE
    # ---------------------------------------------------------
    def _handle_pass_stable(self, program, machine):
        pid = program.current_pass
        print(f"[PROGRAM_ENGINE] PASS {pid} STABLE → DISPENSE START")

        if not machine.is_dispense_window():
            return


        dispense_ml = self._expected_ml_for_pass(pid)

        p = program.passes.get(pid)
        if p:
            p.expected_paint = dispense_ml


        self.executor.send_command({
            "name": "dispense.start",
            "payload": {
                "amount_ml": dispense_ml,
                "pass_id": pid
            }
        })


        # cmd = {
        #     "cmd_id": str(uuid.uuid4()),
        #     "deviceId": "1",
        #     "name": "startWorkflow",
        #     "type": "workflow",
        #     "payload": {
        #         "workflow": "dispense_standard",
        #         "amount_ml": dispense_ml
        #     },
        #     "issued_at": time.time(),
        #     "valid_until": time.time() + 10,
        #     "priority": 10,
        # }

        # # Send command to executor
        # self.executor.queue_command(cmd)

    # ---------------------------------------------------------
    # When plate exits → END DISPENSE
    # ---------------------------------------------------------
    def _handle_pass_exit(self, program):
        pid = program.current_pass
        print(f"[PROGRAM_ENGINE] PASS {pid} EXIT → DISPENSE END")

        dispense_ml = self._expected_ml_for_pass(pid)
        p = program.passes.get(pid)
        if p:
            p.expected_paint = dispense_ml

        self.executor.send_command({
            "name": "dispense.stop",
            "payload": {
                "pass_id": pid
            }
        })

    def _maybe_trigger_refill(self, machine):

        now = time.time()
        pot_kg = machine.pot_weight_kg

        from app.state.system_state import system_state, SystemPhase

        if program_state.phase in (
            ProgramPhase.ABORT,
            ProgramPhase.FAULT,
        ):
            self.refill_state = "IDLE"
            return

        # Hard phase gate
        if program_state.phase not in (
            ProgramPhase.STARTUP,
            ProgramPhase.READY,
            ProgramPhase.RUNNING,
        ):
            return

        if system_state.phase not in (SystemPhase.READY, SystemPhase.STARTUP):
            return

        # -----------------------------------------
        # 1. Unlock refill if pot recovered
        # -----------------------------------------
        # if self.refill_state == "RUNNING":
        #     if pot_kg >= self.refill_target_kg:
        #         print("[PROGRAM_ENGINE] Refill completed (target reached)")
        #         self.refill_state = "IDLE"
        #         self.refill_attempts = 0
        #     return

        # -----------------------------------------
        # 2. Only trigger below threshold
        # -----------------------------------------
        # -----------------------------------------
        # Trigger only below threshold
        # -----------------------------------------
        if pot_kg >= self.refill_threshold_kg:
            return


        # -----------------------------------------
        # 3. Cooldown protection
        # -----------------------------------------
        if now - self.last_refill_ts < self.refill_cooldown_sec:
            return

        # -----------------------------------------
        # 4. If already requested → wait
        # -----------------------------------------
        if self.refill_state != "IDLE":
            return

        # -----------------------------------------
        # 5. If firmware busy → do nothing
        # -----------------------------------------
        if self.executor.is_busy():
            return
        

        print(f"[PROGRAM_ENGINE] Triggering refill (pot={pot_kg:.2f}kg)")

        if self.refill_attempts >= self.max_refill_attempts:
            print("[PROGRAM_ENGINE] Refill lockout – max attempts reached")
            return

        self.executor.send_command({
            "name": "refill.start",
            "payload": {}
        })

        self.refill_attempts += 1
        self.refill_state = "REQUESTED"
        self.last_refill_ts = now

        # self.executor.send_command({
        #     "name": "refill.start",
        #     "payload": {}
        # })

        # self.refill_state = "REQUESTED"
        # self.last_refill_ts = now

  # ---------------------------------------------------------
    # helper
    # ---------------------------------------------------------
    def _expected_ml_for_pass(self, pid):
        passes = self.config.get("passes", {})
        if str(pid) in passes:
            return passes[str(pid)].get("dispense_ml", 5)
        return 5


# global instance injected in app.main
program_engine = None
