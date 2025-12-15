import json

class AckListener:
    def __init__(self, mqtt_client, executor=None):
        self.mqtt = mqtt_client      # EdgeMQTT instance
        self.executor = executor
        self.topic = "devices/+/acks"

    def start(self):
        # Only subscribe — do NOT override on_message
        print("[ACK LISTENER] Subscribing to", self.topic)
        self.mqtt.client.subscribe(self.topic)
