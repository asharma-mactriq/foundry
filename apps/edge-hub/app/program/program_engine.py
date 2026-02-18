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

            if program.phase == ProgramPhase.STARTUP:
                self.executor.send_command({
                    "name": "startup.sequence",
                    "payload": {}
                })

            return


        # --------------------------------------------------
        # NORMAL PASS LOGIC
        # --------------------------------------------------

        if program.phase not in (
            ProgramPhase.READY,
            ProgramPhase.RUNNING
        ):
            return

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


        # stop_cmd = {
        #     "cmd_id": str(uuid.uuid4()),
        #     "deviceId": "1",
        #     "name": "stopWorkflow",
        #     "type": "workflow",
        #     "payload": {},
        #     "issued_at": time.time(),
        #     "valid_until": time.time() + 10,
        #     "priority": 10,
        # }

        # self.executor.queue_command(stop_cmd)

        # if last pass, finish program
        # if pid >= self.config["total_passes"]:
        if self.config and pid >= self.config.get("total_passes", 0):
            print("[PROGRAM_ENGINE] PROGRAM COMPLETED")
            self.stop_program()

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
