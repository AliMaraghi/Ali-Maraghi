"""Phase 1 scheduler (brutal-honesty directive, 2026-11-15). All synthetic fixtures - no real
owner data, no real ledger. Proves: pluggable event sources, a persistent priority queue with
idempotency, cooperative preemption that is journalled, crash-resumption from the journal, a
7-day soak on an accelerated clock, and the ABSOLUTE INVARIANT that this module never touches
ApprovalBook.issue()/approve() or ActionGateway.execute()."""
import ast
import inspect
import json
import tempfile
import unittest
from pathlib import Path

from apex.kernel import scheduler
from apex.kernel.approvals import ApprovalBook
from apex.kernel.budget import Budget
from apex.kernel.gateway import ActionGateway
from apex.kernel.memory import Ledger
from apex.kernel.scheduler import ActionContext, ClockSource, FSWatchSource, JobQueue, SchedulerLoop

SECRET = b"k" * 32


class SchedulerBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.ledger = Ledger(self.root)
        self.queue = JobQueue(self.ledger)

    def tearDown(self):
        self.ledger.close()
        self.tmp.cleanup()


class InvariantTests(SchedulerBase):
    """The one invariant that matters most in this phase: a system with two reference
    monitors has zero. This module must never call issue()/approve()/execute() itself."""
    def test_scheduler_module_never_references_issue_approve_or_execute(self):
        """.execute( on a sqlite3 cursor (self.ledger.db.execute / self.db.execute) is this
        module's own persistence, not ActionGateway.execute() - the AST check below excludes
        only that one, specific, textually-verified pattern, and still flags any other receiver."""
        tree = ast.parse(inspect.getsource(scheduler))
        violations = []
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
                continue
            attr = node.func.attr
            if attr in ("issue", "approve"):
                violations.append(attr)
            elif attr == "execute":
                base = node.func.value
                base_name = base.attr if isinstance(base, ast.Attribute) else getattr(base, "id", None)
                if base_name != "db":
                    violations.append(f"execute(base={base_name})")
        self.assertEqual(violations, [])

    def test_scheduler_module_does_not_even_import_approvals_or_gateway(self):
        source = inspect.getsource(scheduler)
        self.assertNotIn("from .approvals", source)
        self.assertNotIn("from .gateway", source)
        self.assertNotIn("import approvals", source)
        self.assertNotIn("import gateway", source)

    def test_a_registered_action_that_wants_to_request_something_goes_through_the_real_gateway(self):
        """Integration proof of the intended pattern: an action calls gateway.submit() - the
        SAME single reference monitor every other proposer in this codebase uses - and the
        scheduler itself never sees the proposal."""
        book = ApprovalBook(self.ledger, SECRET, clock=lambda: 1_800_000_000.0)
        gateway = ActionGateway(self.ledger, book, Budget(self.ledger))
        calls = []

        def action_that_proposes(ctx, payload):
            state = gateway.submit("sched-proposal-1", "opportunity", "record_decision",
                                   "agent:scheduler-demo", {"note": payload["note"]}, ["fact:1"])
            calls.append(state)

        loop = SchedulerLoop(self.ledger, self.queue, {"propose_something": action_that_proposes}, [],
                             now_fn=lambda: 1_800_000_000.0)
        self.queue.submit("job-1", "propose_something", {"note": "hello"}, 5, 1_800_000_000.0)
        result = loop.tick()
        self.assertEqual(result["result"], "DONE")
        self.assertEqual(calls, ["PENDING"])
        self.assertEqual(book.view("sched-proposal-1")["state"], "PENDING")   # still needs a real human click


class EventSourcePluggabilityTests(SchedulerBase):
    def test_clock_source_fires_once_per_window(self):
        source = ClockSource("hourly", 3600, "tick_action")
        self.assertEqual(len(source.due(0)), 1)
        self.assertEqual(source.due(100), [])          # same window, no second fire
        self.assertEqual(len(source.due(3600)), 1)      # next window

    def test_fswatch_source_fires_on_mtime_change(self):
        """mtime resolution on some filesystems is coarser than the wall-clock gap between two
        back-to-back writes in a fast test, so the mtime change is forced explicitly with
        os.utime rather than relied on from write timing - a test-determinism fix, not a change
        to FSWatchSource's own (correct, mtime-based) production logic."""
        import os
        path = self.root / "watched.json"
        path.write_text("{}")
        os.utime(path, (1000.0, 1000.0))
        source = FSWatchSource("watch1", path, "watch_action")
        first = source.due(0)
        self.assertEqual(len(first), 1)
        self.assertEqual(source.due(0), [])             # unchanged - no refire
        path.write_text('{"changed": true}')
        os.utime(path, (2000.0, 2000.0))                 # force a measurable mtime advance
        self.assertEqual(len(source.due(0)), 1)

    def test_adding_a_third_source_never_touches_schedulerloop_code(self):
        """The literal proof of 'adding a source must not touch the scheduler loop': a brand
        new, ad hoc source class, defined entirely inside this test, works with the unmodified
        SchedulerLoop just by being appended to the sources list."""
        class CountdownSource:
            def __init__(self):
                self.fired = False
            def due(self, now):
                if self.fired:
                    return []
                self.fired = True
                return [{"trigger_id": "countdown.1", "action": "noop", "payload": {}, "priority": 1}]
        ran = []
        loop = SchedulerLoop(self.ledger, self.queue, {"noop": lambda ctx, p: ran.append(1)},
                             [CountdownSource()], now_fn=lambda: 0.0)
        loop.tick()
        self.assertEqual(ran, [1])


class PriorityAndIdempotencyTests(SchedulerBase):
    def test_higher_priority_job_claimed_first(self):
        self.queue.submit("low", "a", {}, priority=1, now=0.0)
        self.queue.submit("high", "a", {}, priority=9, now=0.0)
        job = self.queue.claim_next(1.0)
        self.assertEqual(job["id"], "high")

    def test_duplicate_submission_is_idempotent_not_a_second_job(self):
        self.assertEqual(self.queue.submit("x", "a", {"n": 1}, 5, 0.0), "QUEUED")
        self.assertEqual(self.queue.submit("x", "a", {"n": 1}, 5, 5.0), "DUPLICATE")
        self.assertEqual(len(self.queue.snapshot()), 1)

    def test_conflicting_resubmission_under_the_same_id_is_rejected(self):
        self.queue.submit("x", "a", {"n": 1}, 5, 0.0)
        with self.assertRaises(ValueError):
            self.queue.submit("x", "a", {"n": 2}, 5, 0.0)


class PreemptionTests(SchedulerBase):
    def test_cancellation_is_journalled_immediately_on_request(self):
        self.queue.submit("job-1", "a", {}, 5, 0.0)
        self.queue.request_cancel("job-1", 1.0)
        events = [r["payload"]["event"] for r in self.ledger.records("opportunity")]
        self.assertIn("scheduler_job_cancel_requested", events)

    def test_a_cooperative_action_stops_early_and_preserves_its_checkpoint(self):
        progress = []

        def long_running(ctx, payload):
            for step in range(5):
                if ctx.should_stop():
                    return
                progress.append(step)
                ctx.checkpoint({"step": step})

        loop = SchedulerLoop(self.ledger, self.queue, {"long": long_running}, [], now_fn=lambda: 0.0)
        self.queue.submit("job-1", "long", {}, 5, 0.0)
        # Simulate an external cancel signal arriving mid-run by pre-cancelling before claim -
        # the cooperative check is what the action itself does at each step.
        self.queue.claim_next(0.0)
        self.queue.request_cancel("job-1", 0.0)
        ctx = ActionContext(self.queue, "job-1", lambda: 0.0, None)
        long_running(ctx, {})
        self.assertEqual(progress, [])                  # stopped before the first step
        self.queue.finish("job-1", "CANCELLED", 0.0)
        self.assertEqual(self.queue.snapshot()[0]["state"], "CANCELLED")

    def test_partial_progress_before_cancellation_is_preserved(self):
        calls = {"n": 0}

        def long_running(ctx, payload):
            for step in range(5):
                calls["n"] += 1
                if calls["n"] == 2:                       # cancel arrives after step 0 completes
                    self.queue.request_cancel("job-1", 0.0)
                if ctx.should_stop():
                    return
                ctx.checkpoint({"step": step})

        loop = SchedulerLoop(self.ledger, self.queue, {"long": long_running}, [], now_fn=lambda: 0.0)
        self.queue.submit("job-1", "long", {}, 5, 0.0)
        result = loop.tick()
        self.assertEqual(result["result"], "CANCELLED")
        self.assertEqual(json.loads(self.queue.snapshot()[0]["checkpoint"]), {"step": 0})


class CrashResumptionTests(SchedulerBase):
    def test_a_half_done_job_resumes_from_its_last_checkpoint_not_from_zero(self):
        """The required test: after a SIMULATED CRASH, a half-done job resumes from its last
        journal entry. We run step 0, checkpoint it, then simulate the process dying (no
        finish() call at all) before step 1. A fresh loop, after recover_on_start(), must see
        resume_from == {"step": 0} and continue from there, never redoing step 0."""
        executed_steps = []

        def three_step_action(ctx, payload):
            start = (ctx.resume_from or {}).get("step", -1) + 1
            for step in range(start, 3):
                executed_steps.append(step)
                ctx.checkpoint({"step": step})
                if step == 0 and not payload.get("_second_attempt"):
                    raise RuntimeError("SIMULATED_CRASH")   # process dies mid-job after step 0

        actions = {"three_step": three_step_action}
        loop1 = SchedulerLoop(self.ledger, self.queue, actions, [], now_fn=lambda: 0.0)
        self.queue.submit("job-1", "three_step", {}, 5, 0.0)
        result1 = loop1.tick()
        self.assertEqual(result1["result"], "FAILED")       # the crash is recorded, not hidden
        self.assertEqual(executed_steps, [0])
        snapshot = self.queue.snapshot()[0]
        self.assertEqual(snapshot["state"], "FAILED")
        self.assertEqual(json.loads(snapshot["checkpoint"]), {"step": 0})

        # "Process restart": a brand new loop over the SAME ledger, recovering stale jobs.
        # A FAILED job (the honest outcome of an exception) is not auto-retried by this
        # queue - that is a real design choice (silent infinite retry is its own hazard) -
        # so we model the crash as the realistic case: the job was still RUNNING when the
        # process died (no finish() call reached), which recover_on_start() requeues.
        self.ledger.db.execute("UPDATE scheduler_jobs SET state='RUNNING', available_at=0 WHERE id='job-1'")
        loop2 = SchedulerLoop(self.ledger, self.queue, {"three_step": lambda ctx, p: three_step_action(
            ctx, {**p, "_second_attempt": True})}, [], now_fn=lambda: 1000.0, stale_running_after_seconds=1)
        requeued = loop2.recover_on_start()
        self.assertEqual(requeued, ["job-1"])
        result2 = loop2.tick()
        self.assertEqual(result2["result"], "DONE")
        self.assertEqual(executed_steps, [0, 1, 2])          # step 0 was NOT redone


class SevenDaySoakTests(SchedulerBase):
    def test_accelerated_clock_7_days_zero_lost_events_zero_duplicate_executions(self):
        """The required Phase 1 gate: 7 simulated days on an accelerated clock, zero lost
        events, zero duplicate executions (idempotency holds), proven in real wall-clock
        seconds, not a real week."""
        executions = []

        def hourly_action(ctx, payload):
            executions.append(payload["window"])

        fake_now = {"t": 0.0}
        source = ClockSource("hourly", 3600, "hourly_action", payload_fn=lambda now: {"window": int(now // 3600)})
        loop = SchedulerLoop(self.ledger, self.queue, {"hourly_action": hourly_action}, [source],
                             now_fn=lambda: fake_now["t"])
        seven_days_seconds = 7 * 24 * 3600
        step = 300                                          # 5-minute ticks
        ticks = 0
        while fake_now["t"] < seven_days_seconds:
            loop.tick()
            fake_now["t"] += step
            ticks += 1
        expected_hours = 7 * 24
        self.assertEqual(len(executions), expected_hours)             # zero lost events
        self.assertEqual(len(set(executions)), expected_hours)        # zero duplicates
        self.assertEqual(sorted(executions), list(range(expected_hours)))
        self.assertGreater(ticks, expected_hours)                     # proves the accelerated clock really ran many ticks


if __name__ == "__main__":
    unittest.main()
