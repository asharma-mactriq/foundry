# apps/edge-hub/app/services/command_store.py

import sqlite3
import json
import time
import os
from typing import Optional

# -------------------------------------------------------------------
# SAFE DATABASE LOCATION
# Creates apps/edge-hub/data/edge_commands.db automatically
# -------------------------------------------------------------------

APP_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
DATA_DIR = os.path.join(APP_ROOT, "data")
os.makedirs(DATA_DIR, exist_ok=True)

DB = os.path.join(DATA_DIR, "edge_commands.db")


# -------------------------------------------------------------------
# COMMAND STORE
# -------------------------------------------------------------------

class CommandStore:
    def __init__(self):
        # check_same_thread=False → allow use in scheduler + ack listener threads
        self.conn = sqlite3.connect(DB, check_same_thread=False)
        self._init()

    def _init(self):
        cur = self.conn.cursor()
        cur.execute("""
        CREATE TABLE IF NOT EXISTS commands (
            cmd_id TEXT PRIMARY KEY,
            deviceId TEXT,
            type TEXT,
            payload TEXT,
            priority INTEGER,
            issued_at REAL,
            valid_until REAL,
            status TEXT,
            last_updated REAL,
            details TEXT
        )
        """)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS command_steps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cmd_id TEXT,
            step_index INTEGER,
            step_type TEXT,
            event TEXT,
            success INTEGER,
            ts REAL,
            details TEXT
        )
        """)
        self.conn.commit()

    def add_step(self, cmd_id, step_index, step_type, event, success=True, details=None):
        cur = self.conn.cursor()
        cur.execute("""
            INSERT INTO command_steps (cmd_id, step_index, step_type, event, success, ts, details)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            cmd_id,
            step_index,
            step_type,
            event,
            1 if success else 0,
            time.time(),
            json.dumps(details or {})
        ))
        self.conn.commit()

    def list_steps(self, cmd_id):
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM command_steps WHERE cmd_id=? ORDER BY id ASC", (cmd_id,))
        rows = cur.fetchall()

        keys = ["id","cmd_id","step_index","step_type","event","success","ts","details"]
        out = []
        for r in rows:
            row = dict(zip(keys, r))
            row["details"] = json.loads(row["details"]) if row["details"] else {}
            out.append(row)

        return out

    # ---------------------------------------------------------------
    # ADD COMMAND
    # ---------------------------------------------------------------
    def add(self, cmd: dict):
        cur = self.conn.cursor()
        cur.execute("""
            INSERT OR REPLACE INTO commands
            (cmd_id, deviceId, type, payload, priority, issued_at, valid_until, status, last_updated, details)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            cmd["cmd_id"],
            cmd["deviceId"],
            cmd["type"],
            json.dumps(cmd.get("payload", {})),
            cmd.get("priority", 10),
            cmd["issued_at"],
            cmd["valid_until"],
            cmd.get("status", "queued"),
            time.time(),
            json.dumps({})
        ))
        self.conn.commit()

    # ---------------------------------------------------------------
    # UPDATE STATUS (acked, expired, failed, completed)
    # ---------------------------------------------------------------
    def update_status(self, cmd_id: str, status: str, details: Optional[dict] = None):
        cur = self.conn.cursor()
        cur.execute("""
        UPDATE commands
        SET status=?, last_updated=?, details=?
        WHERE cmd_id=?
        """, (
            status,
            time.time(),
            json.dumps(details or {}),
            cmd_id
        ))
        self.conn.commit()

    # ---------------------------------------------------------------
    # GET ONE COMMAND
    # ---------------------------------------------------------------
    def get(self, cmd_id):
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM commands WHERE cmd_id=?", (cmd_id,))
        row = cur.fetchone()
        if not row:
            return None

        keys = [
            "cmd_id","deviceId","type","payload","priority",
            "issued_at","valid_until","status","last_updated","details"
        ]
        obj = dict(zip(keys, row))
        obj["payload"] = json.loads(obj["payload"]) if obj["payload"] else {}
        obj["details"] = json.loads(obj["details"]) if obj["details"] else {}
        return obj

    # ---------------------------------------------------------------
    # LIST RECENT COMMANDS
    # ---------------------------------------------------------------
    def list_recent(self, limit=200):
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM commands ORDER BY last_updated DESC LIMIT ?", (limit,))
        rows = cur.fetchall()

        keys = [
            "cmd_id","deviceId","type","payload","priority",
            "issued_at","valid_until","status","last_updated","details"
        ]

        out = []
        for r in rows:
            o = dict(zip(keys, r))
            o["payload"] = json.loads(o["payload"]) if o["payload"] else {}
            o["details"] = json.loads(o["details"]) if o["details"] else {}
            out.append(o)
        return out


# -------------------------------------------------------------------
# GLOBAL INSTANCE
# -------------------------------------------------------------------
command_store = CommandStore()
