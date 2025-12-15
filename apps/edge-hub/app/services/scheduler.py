import time
import threading
import json

from app.services.command_store import command_store


class Scheduler:
    def __init__(self, mqtt_client=None, interval_ms=100, max_retries=3, base_timeout=0.5):
        self.mqtt_client = mqtt_client    # <-- store reference
        self.interval = interval_ms / 1000.0
        self.max_retries = max_retries
        self.base_timeout = base_timeout
        self.running = False

    def set_mqtt(self, mqtt_client):
        """Inject MQTT after creation"""
        self.mqtt_client = mqtt_client

    def start(self):
        if self.running:
            return
        self.running = True
        threading.Thread(target=self._loop, daemon=True).start()
        print("[SCHEDULER] Started")

    def stop(self):
        self.running = False

    def _loop(self):
        while self.running:
            now = time.time()
            rows = command_store.list_recent(500)

            for r in rows:
                # TTL
                if r["status"] in ("queued", "sent", "resent"):
                    if now > r["valid_until"]:
                        command_store.update_status(
                            r["cmd_id"], "expired", {"reason": "ttl"}
                        )
                        continue

                # Retry logic
                if r["status"] in ("sent", "resent"):

                    last = r["last_updated"]
                    details = r.get("details", {})
                    retries = details.get("retries", 0)
                    timeout = self.base_timeout * (1 + retries)

                    if now - last > timeout and retries < self.max_retries:
                        if self.mqtt_client:
                            self.mqtt_client.publish(
                                f"devices/{r['deviceId']}/commands",
                                json.dumps(r)
                            )
                        details["retries"] = retries + 1
                        command_store.update_status(r["cmd_id"], "resent", details)
                        print("[SCHEDULER] resent", r["cmd_id"], "retries=", details["retries"])

                    elif retries >= self.max_retries:
                        command_store.update_status(
                            r["cmd_id"], "failed", {"reason": "max_retries"}
                        )

            time.sleep(self.interval)


# global scheduler instance
scheduler = Scheduler()
