import heapq
import time

class CommandQueue:
    def __init__(self):
        self.q = []  # priority queue of tuples: (-priority, cmd_dict)
        self.counter = 0

    def push(self, cmd: dict):
        # priority must come from dict
        # priority = cmd.get("priority", 10)
        self.counter += 1
        heapq.heappush(self.q, (cmd["priority"], self.counter, cmd))


    def pop_valid(self):
        now = time.time()
        while self.q:
            _, _, cmd = heapq.heappop(self.q)

            # TTL check
            valid_until = cmd.get("valid_until", now + 999)
            if now <= valid_until:
                return cmd

            # command expired — skip and continue
        return None


command_queue = CommandQueue()
