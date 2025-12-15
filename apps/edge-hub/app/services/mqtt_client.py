import json
import paho.mqtt.client as mqtt

from app.state.machine_state import machine_state_manager
from app.services.telemetry_service import telemetry_service

class EdgeMQTT:
    def __init__(self, host="127.0.0.1", port=1883, machine_id="1"):
        self.host = host
        self.port = port
        self.machine_id = machine_id
        self.executor = None

        self.client = mqtt.Client(
            client_id=f"edge-{machine_id}",
            userdata=self
        )

        self.client.on_connect = EdgeMQTT._on_connect
        self.client.on_message = EdgeMQTT._on_message

    def connect(self):
        print(f"[MQTT] Connecting to {self.host}:{self.port}")
        try:
            self.client.connect(self.host, self.port, 60)
            self.client.loop_start()
            print("[MQTT] Connected OK")
            return True
        except Exception as e:
            print("[MQTT] Connect ERROR:", e)
            return False

    @staticmethod
    def _on_connect(client, userdata, flags, rc):
        self_ref = userdata
        print(f"[MQTT] on_connect → rc={rc}")

        base = f"machine/{self_ref.machine_id}"
        topics = [
            f"{base}/workflow/complete",
            f"{base}/workflow/event",
            f"{base}/status",            # <-- ESP32 telemetry
            f"devices/{self_ref.machine_id}/acks"    # <-- ACKS optional
            f"{base}/acks"  
        ]

        for t in topics:
            client.subscribe(t)
            print("[MQTT] Subscribed →", t)

    @staticmethod
    def _on_message(client, userdata, message):
        # print("\n[ON_MESSAGE] CALLBACK FIRED!")
        # print("client_id:", client._client_id)
        # print("topic:", message.topic)
        # print("payload:", message.payload)

        self_ref = userdata

        try:
            payload = message.payload.decode()
            data = json.loads(payload)
        except Exception as e:
            print("[MQTT] JSON ERROR", e)
            return

        # ---------------------------------------
        # ACK HANDLER
        # ---------------------------------------
        # if message.topic.endswith("/acks"):
        #     print("[ACK] Received:", data)
        #     cmd_id = data.get("cmd_id")
        #     if self_ref.executor:
        #         self_ref.executor.ack_received(cmd_id, data)
        #     return
        
        if message.topic.endswith("/acks"):
            print("[ACK] Received:", data)

            event = data.get("event")

            # STEP EVENT (command.step)
            if event == "command.step":
                if self_ref.executor:
                    self_ref.executor.step_ack_received(data)
                return

            # LIFECYCLE EVENT (command.received, command.started, command.completed)
            if event in ("command.received", "command.started", "command.completed"):
                if self_ref.executor:
                    self_ref.executor.lifecycle_ack_received(data)
                return

            # OLD BASIC ACK (cmd_id only)
            cmd_id = data.get("cmd_id")
            if cmd_id and self_ref.executor:
                self_ref.executor.ack_received(cmd_id, data)
            return


        # ---------------------------------------
        # WORKFLOW COMPLETE
        # ---------------------------------------
        elif message.topic.endswith("/workflow/complete"):
            workflow = data.get("workflow")
            cmd_id = data.get("cmd_id")

            print(f"[MQTT] Workflow complete → workflow={workflow}, cmd_id={cmd_id}")

            if workflow and cmd_id:
                # Notify executor
                if self_ref.executor:
                    self_ref.executor.workflow_complete_received(workflow, cmd_id)

                # ⭐⭐⭐ NEW: Forward FINAL ACK to Nest Backend ⭐⭐⭐
                try:
                    import httpx
                    backend_url = "http://localhost:3001/api/acks"  # adjust if needed
                    ack_payload = {
                        "cmd_id": cmd_id,
                        "status": "acked",
                        "workflow": workflow
                    }
                    print("[EDGE → BACKEND] Forwarding final ACK:", ack_payload)

                    # async-friendly inside sync context
                    import anyio
                    async def send_ack():
                        async with httpx.AsyncClient() as client:
                            await client.post(backend_url, json=ack_payload)

                    anyio.run(send_ack)

                except Exception as e:
                    print("[EDGE] ERROR forwarding final ACK:", e)

            else:
                print("[MQTT] Invalid workflow complete payload:", data)

            return

        # ---------------------------------------
        # WORKFLOW EVENT
        # ---------------------------------------
        if message.topic.endswith("/workflow/event"):
            print("[MQTT] Event:", data)
            return

        # ---------------------------------------
        # RAW STATUS TELEMETRY FROM ESP32
        # ---------------------------------------
        if message.topic.endswith("/status"):
            # print("[MQTT] Status:", data)

            # # ⭐ Send to machine state
            # # state = machine_state_manager.apply_telemetry(data)
            # # print("[STATE] Updated:", state)

            # # ⭐ Forward to telemetry service (NestJS)
            # telemetry_service.update(data)

            return

    def publish(self, topic, payload):
        self.client.publish(topic, payload)
    
    

def connect_mqtt(host="127.0.0.1", port=1883, machine_id="1"):
    client = EdgeMQTT(host, port, machine_id)
    if client.connect():
        return client
    return None
