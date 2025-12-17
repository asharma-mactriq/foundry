from fastapi import FastAPI
import traceback
import os
from app.api import telemetry, commands, modes
from app.services.mqtt_client import connect_mqtt
from app.services.command_executor import CommandExecutor
from app.commands import command_dispatcher
from app.services.ack_listener import AckListener
from app.services.telemetry_service import telemetry_service
from app.services.scheduler import scheduler
from app.api.registry import router as registry_router
from app.api.program import router as program_router
from app.services.rule_engine import get_rule_engine
from app.api.acks import router as acks_router

app = FastAPI(title="Mactriq Edge Engine")

# ROOT = os.path.dirname(os.path.abspath(__file__))
# RULE_PATH = os.path.join(ROOT, "..", "rules", "rule-registry.json")

RULE_PATH = "/Users/apple/Desktop/foundry/apps/edge-hub/app/rules/rule-registry.json"

def _log(msg: str):
    print(f"[MAIN] {msg}")


@app.on_event("startup")
def startup_event():
    _log("startup_event triggered")

    # ------------------ CONFIG ------------------
    app.state.config = {
        "BACKEND_ACK_URL": "http://localhost:3001/command-acks"
    }

    try:
        # ---------- MQTT (create only here) ----------
        _log("1. Creating MQTT client via connect_mqtt()")
        mqtt_client = connect_mqtt()          # connect_mqtt() should call connect() internally
        if not mqtt_client:
            raise RuntimeError("MQTT not connected")
        app.state.mqtt_client = mqtt_client
        _log("1A. MQTT client created and connected")
        _log(f"1B. Paho client id: {mqtt_client.client._client_id}")

        # ---------- Command Dispatcher ----------
        _log("2. Creating Command Dispatcher")
        command_dispatcher.dispatcher = command_dispatcher.CommandDispatcher(
            mqtt_client.client
        )
        app.state.dispatcher = command_dispatcher.dispatcher
        _log("2A. Dispatcher ready")

        # ---------- Command Executor ----------
        _log("3. Starting Command Executor")
        executor = CommandExecutor(mqtt_client)
        executor.start()
        mqtt_client.executor = executor
        app.state.executor = executor
        _log("3A. Executor started")

        # ---------- ACK Listener ----------
        _log("4. Starting ACK Listener")
        ack = AckListener(mqtt_client, executor)
        ack.start()
        app.state.ack_listener = ack
        _log("4A. ACK Listener started")

        # ---------- Telemetry service ----------
        _log("5. Injecting telemetry service")
        telemetry_service.set_mqtt_client(mqtt_client.client)
        _log("5A. Telemetry service injected")

        # ---------- Rule Engine (NEW) ----------
        rule_engine = get_rule_engine(
            mqtt_client=mqtt_client.client,
            executor=executor,
            workflow_executor=None  # fill if needed later
        )

        # Load startup rules
        rule_engine.load_rules_from_file(RULE_PATH)

        # Subscribe so NestJS can send rules
        def _on_rules_message(client, userdata, msg):
            import json
            try:
                arr = json.loads(msg.payload.decode())
                rule_engine.set_rules(arr)
                print("[RULE ENGINE] Rules updated via MQTT")
            except Exception as e:
                print("[RULE ENGINE] Update error:", e)

        mqtt_client.client.subscribe("edge/rules/update")
        mqtt_client.client.message_callback_add("edge/rules/update", _on_rules_message)


        # ---------- Scheduler ----------
        _log("6. Starting scheduler")
        scheduler.set_mqtt(mqtt_client)   # <---- IMPORTANT
        scheduler.start()
        _log("6A. Scheduler started")

        _log("Startup complete — Edge Hub ready")

    except Exception as e:
        _log("Startup ERROR")
        traceback.print_exception(type(e), e, e.__traceback__)
        raise


@app.on_event("shutdown")
def shutdown_event():
    _log("shutdown_event triggered")
    try:
        # optional: stop scheduler/executor/ack listener if they expose stop()
        try:
            scheduler.stop()
            _log("Scheduler stopped")
        except Exception:
            pass

        # if executor has a stop method
        try:
            exec_obj = getattr(app.state, "executor", None)
            if exec_obj and hasattr(exec_obj, "running"):
                exec_obj.running = False
                _log("Executor flagged to stop")
        except Exception:
            pass

        _log("Shutdown complete")
    except Exception as e:
        traceback.print_exception(type(e), e, e.__traceback__)


# Routers
app.include_router(telemetry.router, prefix="/telemetry")
app.include_router(commands.router, prefix="/commands")
app.include_router(modes.router, prefix="/modes")
app.include_router(registry_router, prefix="/commands")
app.include_router(program_router, prefix="/program")
app.include_router(acks_router, prefix="/api")
