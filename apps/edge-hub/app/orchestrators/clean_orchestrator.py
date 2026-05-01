# app/orchestrators/clean_orchestrator.py

import time
from app.commands.helpers import create_and_queue_command


class CleanOrchestrator:
    def __init__(self):
        self._reset()

    def _reset(self):
        self._active = False
        self._cycles_total = 0
        self._cycles_done = 0
        self._flush_ms = 8000
        self._cycle_cmd_id = None
        self._waiting_for_complete = False

    def start(self, cycles: int, flush_ms: int):
        self._cycles_total = max(1, cycles)
        self._flush_ms = min(flush_ms, 55000)
        self._cycles_done = 0
        self._cycle_cmd_id = None
        self._waiting_for_complete = False
        self._active = True
        print(f"[CLEAN_ORCH] Starting {self._cycles_total} cycles, flush={self._flush_ms}ms")

    def is_active(self):
        return self._active

    def process(self):
        if not self._active:
            return

        # Waiting for current cycle to complete
        if self._waiting_for_complete:
            if self._cycle_cmd_id:
                from app.services.command_store import command_store
                cmd = command_store.get(self._cycle_cmd_id)
                if cmd and cmd.get("status") == "completed":
                    self._cycles_done += 1
                    self._waiting_for_complete = False
                    self._cycle_cmd_id = None
                    print(f"[CLEAN_ORCH] Cycle {self._cycles_done}/{self._cycles_total} done")
            return

        # All cycles done
        if self._cycles_done >= self._cycles_total:
            print("[CLEAN_ORCH] All cycles complete")
            self._reset()
            return

        # Fire next cycle
        print(f"[CLEAN_ORCH] Firing cycle {self._cycles_done + 1}/{self._cycles_total}")
        self._cycle_cmd_id = create_and_queue_command(
            name="system.clean",
            payload={"cycles": 1, "flush_ms": self._flush_ms}
        )
        self._waiting_for_complete = True


clean_orchestrator = CleanOrchestrator()