"""Scheduler (Phase 1, brutal-honesty directive, 2026-11-15).

DISTINCT FROM kernel/jobs.py + kernel/workflow.py on purpose: that pair is a specialized
queue bound to one task shape (Task/Case -> discovery.propose(), replay-on-identical-request).
This module schedules arbitrary registered CALLABLE actions, triggered by pluggable event
sources, with a persistent priority queue, idempotency keys, cooperative preemption and
crash-resumption from the journal. It does not replace jobs.py; nothing here duplicates its
evidence-workflow semantics.

PREEMPTION IS COOPERATIVE, STATED HONESTLY: Python has no safe way to force-kill an arbitrary
callable mid-statement without risking a half-written side effect or a corrupted lock -
kernel/workflow.py already documents its own time budget the same way
("COOPERATIVE_POST_STAGE_NOT_PREEMPTIVE"). "Preemption" here means: a cancellation is
requested and JOURNALLED immediately (so it is visible and auditable the instant it is
asked for), and a well-behaved action checks ActionContext.should_stop() at its own
checkpoints and exits early when true. An action that never checks is not interrupted by
force - exactly as true of every cooperative scheduler, and unlike claiming an action was
"killed" when it was not.

ABSOLUTE INVARIANT, enforced by never importing or referencing it: nothing in this module
calls ApprovalBook.issue()/approve() or ActionGateway.execute(). This module does not import
kernel.approvals or kernel.gateway at all. A registered action that wants to request
something calls gateway.submit() itself, exactly like every other proposer in this codebase
(agents_runtime.py's AgentRunner, propose_capability.py) - this module only decides WHEN an
action runs, never WHETHER its request is approved. Proven by tests/test_scheduler.py's
AST scan of this file's own source.
"""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

from .engine import canonical
from .schema import identifier


def _event_key(prefix: str) -> str:
    """A uuid suffix, not just a timestamp: two journal events for the same job within the
    same clock tick (realistic under a coarse or test-injected now_fn) must never collide on
    the Ledger's own idempotency key - each real occurrence gets its own key regardless of
    clock resolution."""
    return identifier(f"{prefix}.{uuid.uuid4().hex[:12]}"[:80])


class ClockSource:
    """Fires once per fixed interval window. No catch-up policy: if the process was down
    across several windows, only the CURRENT window fires on the next tick - this is a
    deliberate, documented choice (a naive catch-up would flood the queue with stale work
    after any outage), not an oversight."""
    def __init__(self, name: str, interval_seconds: float, action: str, payload_fn=lambda now: {}, priority: int = 5):
        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be positive")
        self.name, self.interval, self.action, self.payload_fn, self.priority = (
            name, interval_seconds, action, payload_fn, priority)
        self._last_window = None

    def due(self, now: float) -> list:
        window = int(now // self.interval)
        if self._last_window is not None and window <= self._last_window:
            return []
        self._last_window = window
        return [{"trigger_id": f"clock.{self.name}.{window}", "action": self.action,
                 "payload": self.payload_fn(now), "priority": self.priority}]


class FSWatchSource:
    """Fires when a watched file's mtime advances. Synthetic-fixture-safe: the path is
    whatever the caller points it at; this module never reads runtime/inbox or runtime/rules
    itself - it only asks `os.stat` for a timestamp of whatever Path it was given."""
    def __init__(self, name: str, path, action: str, payload_fn=lambda path: {}, priority: int = 5):
        self.name, self.path, self.action, self.payload_fn, self.priority = name, Path(path), action, payload_fn, priority
        self._last_mtime = None

    def due(self, now: float) -> list:
        if not self.path.is_file():
            return []
        mtime = self.path.stat().st_mtime
        if self._last_mtime is not None and mtime <= self._last_mtime:
            return []
        self._last_mtime = mtime
        return [{"trigger_id": f"fswatch.{self.name}.{str(mtime).replace('.', '_')}", "action": self.action,
                 "payload": self.payload_fn(self.path), "priority": self.priority}]


class JobQueue:
    """Persistent priority queue with idempotency keys and a per-job checkpoint column -
    the crash-resumption primitive. Every state transition is journalled to the existing
    hash-chained Ledger."""
    STATES = ("QUEUED", "RUNNING", "DONE", "FAILED", "CANCELLED")

    def __init__(self, ledger):
        self.ledger = ledger
        ledger.db.executescript("""
            CREATE TABLE IF NOT EXISTS scheduler_jobs (
              id TEXT PRIMARY KEY, action TEXT NOT NULL, payload TEXT NOT NULL,
              priority INTEGER NOT NULL, state TEXT NOT NULL, checkpoint TEXT,
              cancel_requested INTEGER NOT NULL DEFAULT 0,
              available_at REAL NOT NULL, created_at REAL NOT NULL);
        """)

    def submit(self, job_id: str, action: str, payload: dict, priority: int, now: float) -> str:
        identifier(job_id)
        with self.ledger.transaction():
            prior = self.ledger.db.execute("SELECT action, payload FROM scheduler_jobs WHERE id=?", (job_id,)).fetchone()
            encoded = canonical(payload)
            if prior:
                if prior != (action, encoded):
                    raise ValueError("Idempotency key conflicts with a differently-shaped prior job")
                return "DUPLICATE"
            self.ledger.db.execute(
                "INSERT INTO scheduler_jobs VALUES (?,?,?,?,?,NULL,0,?,?)",
                (job_id, action, encoded, priority, "QUEUED", now, now))
            self.ledger._append(_event_key(f"sched.{job_id}.submitted"), "decision", "opportunity",
                                {"event": "scheduler_job_submitted", "job_id": job_id, "action": action})
            return "QUEUED"

    def claim_next(self, now: float):
        with self.ledger.transaction():
            row = self.ledger.db.execute(
                "SELECT id, action, payload, checkpoint FROM scheduler_jobs "
                "WHERE state='QUEUED' AND available_at<=? ORDER BY priority DESC, available_at ASC, id ASC LIMIT 1",
                (now,)).fetchone()
            if row is None:
                return None
            job_id = row[0]
            self.ledger.db.execute("UPDATE scheduler_jobs SET state='RUNNING', available_at=? WHERE id=?", (now, job_id))
            self.ledger._append(_event_key(f"sched.{job_id}.claimed"), "decision", "opportunity",
                                {"event": "scheduler_job_claimed", "job_id": job_id})
            return {"id": job_id, "action": row[1], "payload": json.loads(row[2]),
                    "checkpoint": json.loads(row[3]) if row[3] else None}

    def requeue_stale_running(self, now: float, stale_after_seconds: float) -> list:
        """The crash-resumption primitive: a job stuck in RUNNING because the process that
        claimed it died without ever calling finish() is requeued (QUEUED) once stale, with
        its last checkpoint intact - a real process restart calls this once at startup, before
        the first tick(). Returns the list of job ids requeued."""
        with self.ledger.transaction():
            rows = self.ledger.db.execute(
                "SELECT id FROM scheduler_jobs WHERE state='RUNNING' AND available_at<=?",
                (now - stale_after_seconds,)).fetchall()
            for (job_id,) in rows:
                self.ledger.db.execute("UPDATE scheduler_jobs SET state='QUEUED', available_at=? WHERE id=?", (now, job_id))
                self.ledger._append(_event_key(f"sched.{job_id}.requeued"), "decision", "opportunity",
                                    {"event": "scheduler_job_requeued_after_crash", "job_id": job_id})
            return [r[0] for r in rows]

    def checkpoint(self, job_id: str, data: dict, now: float) -> None:
        with self.ledger.transaction():
            self.ledger.db.execute("UPDATE scheduler_jobs SET checkpoint=? WHERE id=?", (canonical(data), job_id))
            self.ledger._append(_event_key(f"sched.{job_id}.checkpoint"), "decision", "opportunity",
                                {"event": "scheduler_job_checkpoint", "job_id": job_id, "data": data})

    def request_cancel(self, job_id: str, now: float) -> None:
        with self.ledger.transaction():
            self.ledger.db.execute("UPDATE scheduler_jobs SET cancel_requested=1 WHERE id=?", (job_id,))
            self.ledger._append(_event_key(f"sched.{job_id}.cancel_requested"), "decision", "opportunity",
                                {"event": "scheduler_job_cancel_requested", "job_id": job_id})

    def is_cancel_requested(self, job_id: str) -> bool:
        row = self.ledger.db.execute("SELECT cancel_requested FROM scheduler_jobs WHERE id=?", (job_id,)).fetchone()
        return bool(row and row[0])

    def finish(self, job_id: str, state: str, now: float) -> None:
        if state not in ("DONE", "FAILED", "CANCELLED"):
            raise ValueError("Invalid terminal state")
        with self.ledger.transaction():
            self.ledger.db.execute("UPDATE scheduler_jobs SET state=? WHERE id=?", (state, job_id))
            self.ledger._append(_event_key(f"sched.{job_id}.{state.lower()}"), "decision", "opportunity",
                                {"event": f"scheduler_job_{state.lower()}", "job_id": job_id})

    def snapshot(self) -> list:
        return [dict(zip(("id", "action", "state", "priority", "checkpoint"), row))
                for row in self.ledger.db.execute("SELECT id, action, state, priority, checkpoint FROM scheduler_jobs ORDER BY id")]


class ActionContext:
    """Handed to a registered action at claim time. `resume_from` is the job's last
    checkpoint (None if this is the first attempt) - this is the whole crash-resumption
    contract: a well-behaved action reads resume_from and skips whatever it already did."""
    def __init__(self, queue: JobQueue, job_id: str, now_fn, resume_from):
        self._queue, self._job_id, self._now_fn, self.resume_from = queue, job_id, now_fn, resume_from

    def checkpoint(self, data: dict) -> None:
        self._queue.checkpoint(self._job_id, data, self._now_fn())

    def should_stop(self) -> bool:
        return self._queue.is_cancel_requested(self._job_id)


class SchedulerLoop:
    """Deliberately tiny: ask every registered source for due triggers, submit each to the
    queue, claim and run the single highest-priority due job. Adding a new EventSource means
    constructing one and appending it to `sources` - this method's own code never changes,
    which is the "adding a source must not touch the scheduler loop" requirement made literal."""
    def __init__(self, ledger, queue: JobQueue, actions: dict, sources: list, now_fn=time.time,
                 stale_running_after_seconds: float = 300):
        self.ledger, self.queue, self.actions, self.sources, self.now_fn = ledger, queue, actions, sources, now_fn
        self.stale_running_after_seconds = stale_running_after_seconds

    def recover_on_start(self) -> list:
        """Call once when the process (re)starts, before the first tick() - requeues anything
        left RUNNING by a process that died without finishing it."""
        return self.queue.requeue_stale_running(self.now_fn(), self.stale_running_after_seconds)

    def tick(self) -> dict | None:
        now = self.now_fn()
        for source in self.sources:
            for trigger in source.due(now):
                self.queue.submit(trigger["trigger_id"], trigger["action"], trigger["payload"],
                                  trigger["priority"], now)
        job = self.queue.claim_next(now)
        if job is None:
            return None
        action = self.actions.get(job["action"])
        if action is None:
            self.queue.finish(job["id"], "FAILED", self.now_fn())
            return {"job_id": job["id"], "result": "FAILED", "reason": "UNKNOWN_ACTION"}
        ctx = ActionContext(self.queue, job["id"], self.now_fn, job["checkpoint"])
        try:
            action(ctx, job["payload"])
        except Exception as exc:
            self.queue.finish(job["id"], "FAILED", self.now_fn())
            return {"job_id": job["id"], "result": "FAILED", "reason": type(exc).__name__}
        state = "CANCELLED" if self.queue.is_cancel_requested(job["id"]) else "DONE"
        self.queue.finish(job["id"], state, self.now_fn())
        return {"job_id": job["id"], "result": state}
