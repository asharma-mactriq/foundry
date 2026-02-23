import heapq
import time
import threading

class CommandQueue:
    def __init__(self):
        self.q = []
        self.counter = 0
        self.lock = threading.Lock()

    def push(self, cmd: dict):
        with self.lock:
            self.counter += 1
            heapq.heappush(self.q, (-cmd["priority"], self.counter, cmd))

    # def pop_valid(self):
    #     now = time.time()
        
    #     with self.lock:
    #         while self.q:
    #             _, _, cmd = heapq.heappop(self.q)
    #             valid_until = cmd.get("valid_until")
    #             if valid_until and now <= valid_until:
    #                 return cmd
    #     return None
    
    def pop_valid(self):
        now = time.time()

        with self.lock:
            while self.q:
                _, _, cmd = heapq.heappop(self.q)

                valid_until = cmd.get("valid_until")

                if valid_until and now > valid_until:
                    from app.services.command_store import command_store
                    command_store.update_status(cmd["cmd_id"], "expired")
                    continue

                return cmd

        return None
    
    def peek_valid(self):
        now = time.time()

        with self.lock:
            # We cannot just look at q[0] because it might be expired.
            # We must scan without modifying heap.

            best_candidate = None

            for priority, counter, cmd in self.q:
                valid_until = cmd.get("valid_until")

                if valid_until and now > valid_until:
                    continue

                # Because heap stores (-priority, counter, cmd),
                # smaller tuple = higher priority.
                if best_candidate is None:
                    best_candidate = (priority, counter, cmd)
                else:
                    if (priority, counter) < (best_candidate[0], best_candidate[1]):
                        best_candidate = (priority, counter, cmd)

            return best_candidate[2] if best_candidate else None



# import heapq
# import time

# class CommandQueue:
#     def __init__(self):
#         self.q = []  # priority queue of tuples: (-priority, cmd_dict)
#         self.counter = 0

#     def push(self, cmd: dict):
#         # priority must come from dict
#         # priority = cmd.get("priority", 10)
#         self.counter += 1
#         heapq.heappush(self.q, (-cmd["priority"], self.counter, cmd))


#     def pop_valid(self):
#         now = time.time()
#         while self.q:
#             _, _, cmd = heapq.heappop(self.q)

#             # TTL check
#             valid_until = cmd.get("valid_until", now + 999)
#             if now <= valid_until:
#                 return cmd

#             # command expired — skip and continue
#         return None


command_queue = CommandQueue()
