# sim_device.py
import json
import time
import paho.mqtt.client as mqtt

DEVICE_ID = "edge1"
CMD_TOPIC = f"devices/{DEVICE_ID}/commands"
ACK_TOPIC = f"devices/{DEVICE_ID}/acks"

client = mqtt.Client(client_id="edge-device")

def on_connect(c, u, f, rc):
    print("DEVICE CONNECTED")
    client.subscribe(CMD_TOPIC)

def on_message(c, u, msg):
    cmd = json.loads(msg.payload.decode())
    print("DEVICE RECEIVED:", cmd)

    ack = {
        "cmd_id": cmd["cmd_id"],
        "deviceId": DEVICE_ID,
        "status": "completed",
        "ts": time.time()
    }
    
    time.sleep(0.1)
    client.publish(ACK_TOPIC, json.dumps(ack))
    print("DEVICE SENT ACK:", ack)

client.on_connect = on_connect
client.on_message = on_message

client.connect("localhost", 1883, 60)
client.loop_forever()
