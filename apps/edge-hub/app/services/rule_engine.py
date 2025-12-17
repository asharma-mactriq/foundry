# app/services/rule_engine.py
import time
import json
import threading
import traceback
from typing import Any, Dict, List
from app.commands.helpers import create_and_queue_command

# If you keep a module-style global 'app' like FastAPI app.state, import it:
# from fastapi import current_app as app  # only available inside request context; use safe access in startup
# Alternatively the startup code will inject mqtt/executor explicitly into RuleEngine

_LOG_PREFIX = "[RULES]"

# -------------------------
# Simple expression evaluator
# -------------------------
# We provide a safe evaluator that supports:
# - logical and/or/not, parentheses
# - comparisons: ==, !=, >, <, >=, <=
# - attribute access like machine.pressure or program.pass_no or raw['flow']
#
# Implementation: parse tokens and evaluate with Python AST in a restricted env.
import ast

class ConditionEvalError(Exception):
    pass

ALLOWED_NODE_TYPES = (
    ast.Expression, ast.BoolOp, ast.UnaryOp, ast.BinOp, ast.Compare,
    ast.Name, ast.Load, ast.Constant, ast.Attribute, ast.Subscript,
    ast.And, ast.Or, ast.Not, ast.Eq, ast.NotEq, ast.Gt, ast.Lt, ast.GtE,
    ast.LtE, ast.Num, ast.Str, ast.List, ast.Tuple, ast.Index, ast.Call
)

def _to_safe_name(name: str):
    # convert '.' to '__' for mapping if you want, but we'll supply a resolver
    return name

def safe_eval_condition(expr: str, context: Dict[str, Any]) -> bool:
    import ast

    try:
        node = ast.parse(expr, mode="eval")
    except Exception as e:
        raise ConditionEvalError(f"parse error: {e}")

    # Validate allowed ast types
    for n in ast.walk(node):
        if not isinstance(n, ALLOWED_NODE_TYPES):
            raise ConditionEvalError(f"disallowed node in condition: {type(n).__name__}")

    # -------- FIXED RESOLVER --------
    def resolver(n):
        # raw name → raw, machine, program
        if isinstance(n, ast.Name):
            return context.get(n.id, None)

        # attribute access: machine.gap_transition
        if isinstance(n, ast.Attribute):
            base = resolver(n.value)
            if base is None:
                return None

            attr = n.attr

            # dict support
            if isinstance(base, dict):
                return base.get(attr)

            # object support
            return getattr(base, attr, None)

        # subscript access: raw['flow']
        if isinstance(n, ast.Subscript):
            base = resolver(n.value)

            # get the key
            key_node = n.slice
            try:
                if isinstance(key_node, ast.Index):
                    key = key_node.value.value
                elif isinstance(key_node, ast.Constant):
                    key = key_node.value
                else:
                    return None
            except:
                return None

            if isinstance(base, dict):
                return base.get(key)
            return None

        if isinstance(n, ast.Constant):
            return n.value

        return None
    # -------- END RESOLVER --------

    # Replace names using eval
    safe_globals = {}

    # locals directly include context so machine, program, raw are available
    safe_locals = context.copy()

    try:
        return bool(eval(compile(node, "<cond>", "eval"), safe_globals, safe_locals))
    except Exception as e:
        raise ConditionEvalError(f"eval error: {e}")

# -------------------------
# Rule & Engine
# -------------------------
class Rule:
    def __init__(self, d: Dict[str, Any]):
        self.id = d.get("id") or f"rule_{int(time.time()*1000)}"
        self.enabled = d.get("enabled", True)
        # higher number = higher priority executed earlier
        self.priority = int(d.get("priority", 100))
        self.condition = d.get("condition", "False")
        self.actions = d.get("actions", [])  # list of action dicts
        self.cooldown_ms = int(d.get("cooldown_ms", 0))
        self.last_fired_ms = 0
        self.meta = d.get("meta", {})

    def can_fire(self) -> bool:
        if not self.enabled:
            return False
        if self.cooldown_ms <= 0:
            return True
        return (time.time() * 1000.0 - self.last_fired_ms) >= self.cooldown_ms

    def mark_fired(self):
        self.last_fired_ms = time.time() * 1000.0

class RuleEngine:
    def __init__(self, mqtt_client=None, executor=None, workflow_executor=None):
        self.lock = threading.Lock()
        self.rules: Dict[str, Rule] = {}
        self.mqtt_client = mqtt_client
        self.executor = executor  # CommandExecutor instance
        self.workflow_executor = workflow_executor
        # action mapping
        self.action_map = {
            "open_valve": self._action_open_valve,
            "close_valve": self._action_close_valve,
            "start_workflow": self._action_start_workflow,
            "stop_workflow": self._action_stop_workflow,
            "stop_program": self._action_stop_program,
            "publish_alert": self._action_publish_alert,
            "pressure_reprime": self._action_pressure_reprime,
            "nop": lambda *a, **k: None,
        }

    # ---------- rule management ----------
    def load_rules_from_file(self, path: str):
        try:
            with open(path, "r") as f:
                arr = json.load(f)
            self.set_rules(arr)
            print(_LOG_PREFIX, f"loaded {len(arr)} rules from {path}")
        except Exception as e:
            print(_LOG_PREFIX, "load error:", e)

    def set_rules(self, arr: List[Dict[str, Any]]):
        with self.lock:
            new = {}
            for d in arr:
                r = Rule(d)
                new[r.id] = r
            self.rules = new
        print(_LOG_PREFIX, f"rules set: {len(self.rules)}")

    def upsert_rule(self, d: Dict[str, Any]):
        r = Rule(d)
        with self.lock:
            self.rules[r.id] = r
        print(_LOG_PREFIX, "upsert rule:", r.id)

    def delete_rule(self, rule_id: str):
        with self.lock:
            if rule_id in self.rules:
                del self.rules[rule_id]

    # ---------- evaluation ----------
    def evaluate_all(self, raw: Dict[str, Any], machine=None, program=None):
        """
        Evaluate rules for the incoming telemetry.
        - raw: raw telemetry dict
        - machine: MachineState object or dict
        - program: ProgramState object or dict
        """
        # Build context for condition eval
        ctx = {
            "raw": raw,
            "machine": machine if machine is not None else {},
            "program": program if program is not None else {}
        }
        fired = []
        # Rules ordered by priority desc (higher first), then id
        with self.lock:
            rules_sorted = sorted(self.rules.values(), key=lambda x: (-x.priority, x.id))
        for rule in rules_sorted:
            if not rule.enabled:
                continue
            if not rule.can_fire():
                continue
            try:
                ok = safe_eval_condition(rule.condition, ctx)
            except ConditionEvalError as e:
                print(_LOG_PREFIX, f"condition eval error for {rule.id}: {e}")
                continue
            except Exception as e:
                print(_LOG_PREFIX, f"unexpected cond eval {rule.id}: {e}")
                continue

            if ok:
                try:
                    self._execute_rule_actions(rule, raw, machine, program)
                    fired.append(rule.id)
                    rule.mark_fired()
                except Exception as e:
                    print(_LOG_PREFIX, f"error executing actions for {rule.id} -> {e}")
                    traceback.print_exc()
        return fired

    # ---------- actions ----------
    def _execute_rule_actions(self, rule: Rule, raw, machine, program):
        audit = {
            "ts": int(time.time() * 1000),
            "rule_id": rule.id,
            "actions": [],
            "raw": raw
        }
        for a in rule.actions:
            if not isinstance(a, dict):
                continue
            t = a.get("type")
            fn = self.action_map.get(t)
            if not fn:
                print(_LOG_PREFIX, "unknown action type", t)
                continue
            # action receives parameters and context
            res = fn(a.get("params", {}), raw=raw, machine=machine, program=program)
            audit["actions"].append({"type": t, "params": a.get("params", {}), "result": bool(res)})
        # publish audit to mqtt if available
        try:
            if self.mqtt_client:
                self.mqtt_client.publish("edge/rules/audit", json.dumps(audit))
        except Exception:
            print(_LOG_PREFIX, "failed to publish rule audit")
        return audit

    # action implementations (safe wrappers)
    def _action_open_valve(self, params, **ctx):
        vid = params.get("valve_id")
        if not vid:
            return False
        # Use CommandExecutor to send command — we assume it exposes .send_command(cmd_dict)
        try:
            cmd_id = create_and_queue_command(
                name="openValve",
                payload={"valve_id": int(vid)}
            )
            print("[RULES] queued command:", cmd_id)
            return True

            # if self.executor:
            #     self.executor.enqueue_command(cmd)
            # fallback: publish mqtt raw command
            # if self.mqtt_client:
            #     self.mqtt_client.publish("devices/esp/commands", json.dumps(cmd))
            #     return True
        except Exception as e:
            print(_LOG_PREFIX, "open_valve error", e)
        return False

    def _action_close_valve(self, params, **ctx):
        vid = params.get("valve_id")
        if not vid:
            return False
        try:
            cmd_id = create_and_queue_command(
                name="openValve",
                payload={"valve_id": int(vid)}
            )
            print("[RULES] queued command:", cmd_id)
            return True
            # if self.mqtt_client:
            #     self.mqtt_client.publish("devices/esp/commands", json.dumps(cmd))
            #     return True
        except Exception as e:
            print(_LOG_PREFIX, "close_valve error", e)
        return False

    def _action_start_workflow(self, params, **ctx):
        wf_name = params.get("workflow")
        if not wf_name:
            return False
        try:
            if self.workflow_executor:
                self.workflow_executor.start_workflow(wf_name, context=ctx)
                return True
            # fallback: publish command to edge executor (if exists)
            if self.mqtt_client:
                self.mqtt_client.publish("edge/commands", json.dumps({"cmd": "start_workflow", "workflow": wf_name}))
                return True
        except Exception as e:
            print(_LOG_PREFIX, "start_workflow error", e)
        return False

    def _action_stop_workflow(self, params, **ctx):
        wf_name = params.get("workflow")
        if self.workflow_executor and wf_name:
            try:
                self.workflow_executor.stop_workflow(wf_name)
                return True
            except Exception as e:
                print(_LOG_PREFIX, "stop_workflow error", e)
        return False

    def _action_stop_program(self, params, **ctx):
        # send a stop command to program engine / workflow executor
        try:
            if self.workflow_executor:
                self.workflow_executor.stop_current_program()
                return True
            if self.mqtt_client:
                self.mqtt_client.publish("edge/commands", json.dumps({"cmd": "stop_program"}))
                return True
        except Exception as e:
            print(_LOG_PREFIX, "stop_program error", e)
        return False

    def _action_publish_alert(self, params, **ctx):
        topic = params.get("topic", "edge/alerts")
        payload = params.get("payload")
        # allow templating from telemetry
        if isinstance(payload, str) and "{raw" in payload:
            try:
                payload = payload.format(raw=ctx.get("raw", {}), machine=ctx.get("machine", {}), program=ctx.get("program", {}))
            except Exception:
                pass
        try:
            if self.mqtt_client:
                self.mqtt_client.publish(topic, json.dumps({"ts": int(time.time()*1000), "payload": payload}))
                return True
        except Exception as e:
            print(_LOG_PREFIX, "publish_alert error", e)
        return False

    def _action_pressure_reprime(self, params, **ctx):
        machine = ctx["machine"]

        pressure = float(getattr(machine, "pressure", 0.0))

        target = 1.8
        min_ms = 500
        max_ms = 5000

        deficit = max(0.0, target - pressure)
        duration_ms = int(deficit * 1000)

        duration_ms = max(min_ms, min(duration_ms, max_ms))

        print(f"[RULES] Auto reprime → {duration_ms} ms")

        create_and_queue_command(
            name="pressure.reprime",
            payload={
                "duration_ms": duration_ms,
                "threshold": target - 0.2
            }
        )
        return True


# Singleton convenience
_rule_engine_instance = None

def get_rule_engine(mqtt_client=None, executor=None, workflow_executor=None):
    global _rule_engine_instance
    if _rule_engine_instance is None:
        _rule_engine_instance = RuleEngine(mqtt_client=mqtt_client, executor=executor, workflow_executor=workflow_executor)
    else:
        # inject dependencies if provided
        if mqtt_client:
            _rule_engine_instance.mqtt_client = mqtt_client
        if executor:
            _rule_engine_instance.executor = executor
        if workflow_executor:
            _rule_engine_instance.workflow_executor = workflow_executor
    return _rule_engine_instance
