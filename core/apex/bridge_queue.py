"""Browser-task queue for the laptop bridge, stored in the local hash-chained journal database.

Only local VPS code (scripts/laptop_task.py, agents) can ENQUEUE. The public endpoint can only hand out a leased task and accept its result. A task is validated twice (here and on the laptop):
https only, allowed hosts only, at most 30 steps of fill / click / wait_for_text. The laptop owner still approves each task with y/N and the agent never types secrets or clicks consent buttons.
"""
from __future__ import annotations

import json
import secrets
import time
from urllib.parse import urlsplit

from .kernel.schema import identifier

ALLOWED_HOSTS = {"console.cloud.google.com", "developers.facebook.com", "console.apexcorelab.uk", "apexcorelab.uk",
                 "enablebanking.com", "accounts.google.com", "wispy-limit-fad4.cloudflareaccess.com"}
ACTIONS = ("fill", "click", "wait_for_text")
TASK_KINDS = ("browser", "notepad_demo")
DEMO_TEXT = "Apex is Alive"
NOTEPAD_TEXT_RE = __import__("re").compile(r"[A-Za-z0-9 ,.!\'-]{1,60}")
MAX_STEPS, MAX_PENDING, LEASE_SECONDS, TTL_SECONDS, MAX_RESULT_BYTES = 30, 20, 900, 86_400, 8192


class QueueError(ValueError):
    pass


def validate_task(purpose, url, steps):
    if not isinstance(purpose, str) or not 1 <= len(purpose) <= 200 or any(ord(c) < 32 for c in purpose):
        raise QueueError("purpose must be 1..200 printable characters")
    parts = urlsplit(url) if isinstance(url, str) and len(url) <= 2000 else None
    if parts is None or parts.scheme != "https" or parts.hostname not in ALLOWED_HOSTS or parts.username or parts.password:
        raise QueueError("url must be https on an allowed host")
    if not isinstance(steps, list) or len(steps) > MAX_STEPS:
        raise QueueError("steps must be a list of at most 30 items")
    clean = []
    for step in steps:
        if not isinstance(step, dict) or set(step) - {"action", "selector", "value"} or step.get("action") not in ACTIONS:
            raise QueueError("invalid step")
        selector, value = step.get("selector"), step.get("value")
        if not isinstance(selector, str) or not 1 <= len(selector) <= 200 or any(ord(c) < 32 for c in selector):
            raise QueueError("invalid selector")
        if value is not None and (not isinstance(value, str) or len(value) > 500):
            raise QueueError("invalid value")
        clean.append({k: v for k, v in (("action", step["action"]), ("selector", selector), ("value", value)) if v is not None})
    return purpose, url, clean


class BridgeQueue:
    def __init__(self, ledger, clock=time.time):
        self.ledger, self.clock = ledger, clock
        ledger.db.executescript("""
            CREATE TABLE IF NOT EXISTS bridge_tasks (
              id TEXT PRIMARY KEY, created REAL NOT NULL, purpose TEXT NOT NULL, url TEXT, steps TEXT NOT NULL, kind TEXT NOT NULL DEFAULT 'browser',
              state TEXT NOT NULL, lease_token TEXT, lease_until REAL, result TEXT, finished REAL);
            CREATE TABLE IF NOT EXISTS bridge_meta (k TEXT PRIMARY KEY, v REAL NOT NULL);
        """)

    def _reserve_slot(self, now):
        self.ledger.db.execute("UPDATE bridge_tasks SET state='EXPIRED' WHERE state IN ('PENDING','LEASED') AND created<?", (now - TTL_SECONDS,))
        if self.ledger.db.execute("SELECT COUNT(*) FROM bridge_tasks WHERE state='PENDING'").fetchone()[0] >= MAX_PENDING:
            raise QueueError("too many pending tasks")
        return "bt" + secrets.token_hex(7)

    def enqueue(self, purpose, url, steps):
        purpose, url, steps = validate_task(purpose, url, steps)
        now = self.clock()
        with self.ledger.transaction():
            task_id = self._reserve_slot(now)
            self.ledger.db.execute("INSERT INTO bridge_tasks (id,created,purpose,url,steps,kind,state) VALUES (?,?,?,?,?,'browser','PENDING')",
                                   (task_id, now, purpose, url, json.dumps(steps)))
            self.ledger._append(identifier(f"bridge.{task_id}.q"), "decision", "personal", {"event": "bridge_task_enqueued", "task": task_id, "host": urlsplit(url).hostname})
        return task_id

    def enqueue_notepad_demo(self, text=DEMO_TEXT):
        """Narrow, non-general demo: the laptop agent opens Notepad on a server-written text file. No selector, no arbitrary command, no typing."""
        if not isinstance(text, str) or not NOTEPAD_TEXT_RE.fullmatch(text):
            raise QueueError("demo text must be 1..60 plain characters")
        now = self.clock()
        with self.ledger.transaction():
            task_id = self._reserve_slot(now)
            self.ledger.db.execute("INSERT INTO bridge_tasks (id,created,purpose,url,steps,kind,state) VALUES (?,?,?,NULL,?,'notepad_demo','PENDING')",
                                   (task_id, now, "Prove the laptop bridge works", json.dumps({"text": text})))
            self.ledger._append(identifier(f"bridge.{task_id}.q"), "decision", "personal", {"event": "bridge_task_enqueued", "task": task_id, "host": "notepad_demo"})
        return task_id

    def touch_poll(self):
        with self.ledger.transaction():
            self.ledger.db.execute("INSERT OR REPLACE INTO bridge_meta VALUES ('last_poll', ?)", (self.clock(),))

    def lease_next(self):
        now = self.clock()
        with self.ledger.transaction():
            row = self.ledger.db.execute(
                "SELECT id,purpose,url,steps,kind FROM bridge_tasks WHERE (state='PENDING' OR (state='LEASED' AND lease_until<?)) AND created>=? ORDER BY created LIMIT 1",
                (now, now - TTL_SECONDS)).fetchone()
            if row is None:
                return None
            token = secrets.token_hex(16)
            self.ledger.db.execute("UPDATE bridge_tasks SET state='LEASED', lease_token=?, lease_until=? WHERE id=?", (token, now + LEASE_SECONDS, row[0]))
        return {"id": row[0], "purpose": row[1], "url": row[2], "steps": json.loads(row[3]), "kind": row[4], "lease_token": token}

    def submit_result(self, task_id, lease_token, result):
        encoded = json.dumps(result, sort_keys=True)
        if len(encoded.encode()) > MAX_RESULT_BYTES:
            raise QueueError("result too large")
        with self.ledger.transaction():
            row = self.ledger.db.execute("SELECT lease_token,state FROM bridge_tasks WHERE id=?", (task_id,)).fetchone()
            if row is None or row[1] != "LEASED" or not secrets.compare_digest(row[0] or "", lease_token or ""):
                return False
            self.ledger.db.execute("UPDATE bridge_tasks SET state='DONE', result=?, finished=? WHERE id=?", (encoded, self.clock(), task_id))
            self.ledger._append(identifier(f"bridge.{task_id}.r"), "decision", "personal", {"event": "bridge_task_done", "task": task_id,
                                                                                         "status": str(result.get("status"))[:40]})
        return True

    def status(self, task_id):
        row = self.ledger.db.execute("SELECT state,result,created,finished FROM bridge_tasks WHERE id=?", (task_id,)).fetchone()
        if row is None:
            raise QueueError("unknown task")
        return {"state": row[0], "result": json.loads(row[1]) if row[1] else None, "created": row[2], "finished": row[3]}

    def summary(self):
        counts = dict(self.ledger.db.execute("SELECT state, COUNT(*) FROM bridge_tasks GROUP BY state"))
        poll = self.ledger.db.execute("SELECT v FROM bridge_meta WHERE k='last_poll'").fetchone()
        return {"counts": counts, "last_poll": poll[0] if poll else None}
