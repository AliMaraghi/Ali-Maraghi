"""Approval console: view-does-not-execute, CSRF, payload binding, replay, expiry, overflow. Synthetic data only."""
import hashlib
import json
import re
import time
import unittest
from http.cookies import SimpleCookie
from unittest.mock import Mock
from urllib.parse import urlencode

import test_google_web
import test_missions
from apex.approvals_web import ApprovalRoutes, is_approvals_path
from apex.console_server import ConsoleApp
from apex.kernel.approvals import ApprovalBook, PROPOSAL_TTL

OWNER = "owner@example.org"
SECRET = "s" * 40


class ApprovalWebTests(unittest.TestCase):
    setUp = test_missions.MissionTests.setUp
    tearDown = test_missions.MissionTests.tearDown
    call = test_google_web.GoogleWebTests.call

    def app(self, clock=time.time):
        path = self.root / "approvals.json"
        path.write_text(json.dumps({"owner": OWNER, "approval_secret": SECRET}))
        path.chmod(0o600)
        self.clock = clock
        routes = ApprovalRoutes(self.root, path, OWNER, clock=clock)
        return ConsoleApp(self.root, Mock(valid=Mock(return_value=True)), None, None, None, routes)

    def seed(self, pid="p1", commentary=None, clock=time.time):
        book = ApprovalBook(self.ledger, SECRET.encode(), clock=clock)
        return book, book.propose(pid, "opportunity", "record_review", "agent:discovery",
                                  {"title": "Synthetic tender <b>x</b>", "value_pence": 0}, ["ev-1"], commentary=commentary)

    def session(self, app, path="/approvals"):
        response, body = self.call(app, path)
        cookie = response["headers"]["Set-Cookie"]
        parsed = SimpleCookie()
        parsed.load(cookie)
        sid = parsed["__Host-apex-owner"].value
        csrf = self.ledger.db.execute("SELECT csrf FROM owner_web_sessions WHERE id=?",
                                      (hashlib.sha256(sid.encode()).hexdigest(),)).fetchone()[0]
        return cookie, csrf, response, body

    def digest(self, pid="p1"):
        return self.ledger.db.execute("SELECT payload_hash FROM proposals WHERE id=?", (pid,)).fetchone()[0]

    def post(self, app, cookie, csrf, action, pid="p1", digest=None, **extra):
        data = urlencode({"csrf": csrf, "payload_hash": digest or self.digest(pid), **extra})
        return self.call(app, f"/approvals/{pid}/{action}", cookie, "POST", data)[0]["status"]

    def test_paths(self):
        self.assertTrue(is_approvals_path("/approvals"))
        self.assertTrue(is_approvals_path("/approvals/p1/approve"))
        self.assertFalse(is_approvals_path("/approvals/../x"))
        self.assertFalse(is_approvals_path("/approvals/p1/explode"))

    def test_owner_gate_and_unconfigured(self):
        app = self.app()
        app.verifier.valid.return_value = False
        self.assertTrue(self.call(app, "/approvals")[0]["status"].startswith("401"))
        bare = ConsoleApp(self.root, Mock(valid=Mock(return_value=True)))
        self.assertTrue(self.call(bare, "/approvals")[0]["status"].startswith("503"))

    def test_viewing_never_executes_or_approves(self):
        app = self.app()
        self.seed()
        cookie, csrf, response, listing = self.session(app)
        self.assertIn(b"p1", listing)
        for _ in range(3):
            response, detail = self.call(app, "/approvals/p1", cookie)
            self.assertTrue(response["status"].startswith("200"))
        state = self.ledger.db.execute("SELECT state FROM proposals WHERE id='p1'").fetchone()[0]
        self.assertEqual(state, "PENDING")
        events = [r["payload"]["event"] for r in self.ledger.records("opportunity")]
        self.assertEqual(events, ["proposed"])
        self.assertIn(self.digest().encode(), detail)

    def test_page_separates_trusted_facts_from_model_commentary_and_escapes(self):
        app = self.app()
        self.seed(commentary="Looks great <script>alert(1)</script>")
        cookie, csrf, _, _ = self.session(app, "/approvals/p1")
        _, body = self.call(app, "/approvals/p1", cookie)
        text = body.decode()
        self.assertLess(text.index("Application-generated facts"), text.index("Model-generated commentary"))
        self.assertIn("Untrusted", text)
        self.assertNotIn("<script>", text)
        self.assertIn("&lt;b&gt;x&lt;/b&gt;", text)
        self.assertIn("Exact action parameters", text)
        self.assertIn("Decision deadline", text)

    def test_post_requires_csrf_origin_and_exact_fields(self):
        app = self.app()
        self.seed()
        cookie, csrf, _, _ = self.session(app, "/approvals/p1")
        self.assertTrue(self.post(app, cookie, "wrong", "approve").startswith("403"))
        bad_origin = self.call(app, "/approvals/p1/approve", cookie, "POST",
                               urlencode({"csrf": csrf, "payload_hash": self.digest()}), origin="https://evil.test")[0]
        self.assertTrue(bad_origin["status"].startswith("403"))
        extra = self.call(app, "/approvals/p1/approve", cookie, "POST",
                          urlencode({"csrf": csrf, "payload_hash": self.digest(), "x": "1"}))[0]
        self.assertTrue(extra["status"].startswith("400"))
        no_session = self.call(app, "/approvals/p1/approve", "", "POST",
                               urlencode({"csrf": csrf, "payload_hash": self.digest()}))[0]
        self.assertTrue(no_session["status"].startswith("403"))
        self.assertEqual(self.ledger.db.execute("SELECT state FROM proposals WHERE id='p1'").fetchone()[0], "PENDING")

    def test_get_on_mutation_path_is_not_allowed(self):
        app = self.app()
        self.seed()
        cookie, _, _, _ = self.session(app)
        self.assertTrue(self.call(app, "/approvals/p1/approve", cookie)[0]["status"].startswith("405"))

    def test_full_flow_approve_execute_and_replay(self):
        app = self.app()
        self.seed()
        cookie, csrf, _, _ = self.session(app, "/approvals/p1")
        self.assertTrue(self.post(app, cookie, csrf, "execute").startswith("403"))      # not yet approved
        self.assertTrue(self.post(app, cookie, csrf, "approve").startswith("303"))
        self.assertTrue(self.post(app, cookie, csrf, "approve").startswith("403"))      # replay
        self.assertTrue(self.post(app, cookie, csrf, "deny").startswith("403"))         # no flip after approval
        self.assertTrue(self.post(app, cookie, csrf, "execute").startswith("303"))
        self.assertTrue(self.post(app, cookie, csrf, "execute").startswith("403"))      # no double execution
        events = [r["payload"]["event"] for r in self.ledger.records("opportunity")]
        self.assertEqual(events, ["proposed", "approved", "executed"])
        self.assertGreaterEqual(self.ledger.verify(), 3)      # chain intact; includes the session event

    def test_denial_flow(self):
        app = self.app()
        self.seed()
        cookie, csrf, _, _ = self.session(app, "/approvals/p1")
        self.assertTrue(self.post(app, cookie, csrf, "deny").startswith("303"))
        self.assertTrue(self.post(app, cookie, csrf, "approve").startswith("403"))
        self.assertEqual(self.ledger.db.execute("SELECT state FROM proposals WHERE id='p1'").fetchone()[0], "DENIED")

    def test_payload_changed_after_display_is_rejected(self):
        app = self.app()
        self.seed()
        cookie, csrf, _, _ = self.session(app, "/approvals/p1")
        shown = self.digest()
        body = '{"evidence":["ev-1"],"payload":{"title":"Swapped","value_pence":0}}'
        new_hash = hashlib.sha256(body.encode()).hexdigest()
        self.ledger.db.execute("UPDATE proposals SET payload=?, payload_hash=? WHERE id='p1'", (body, new_hash))
        self.assertTrue(self.post(app, cookie, csrf, "approve", digest=shown).startswith("403"))
        self.assertEqual(self.ledger.db.execute("SELECT state FROM proposals WHERE id='p1'").fetchone()[0], "PENDING")

    def test_unanswered_proposal_expires_and_cannot_be_approved(self):
        now = [1_800_000_000.0]
        app = self.app(clock=lambda: now[0])
        self.seed(clock=lambda: now[0])
        cookie, csrf, _, _ = self.session(app, "/approvals/p1")
        now[0] += PROPOSAL_TTL + 5
        self.assertTrue(self.post(app, cookie, csrf, "approve").startswith("403"))
        self.assertEqual(self.ledger.db.execute("SELECT state FROM proposals WHERE id='p1'").fetchone()[0], "EXPIRED")

    def test_overflow_defers_then_releases_next_day_without_approving(self):
        now = [1_800_000_000.0]
        book = ApprovalBook(self.ledger, SECRET.encode(), clock=lambda: now[0])
        states = [book.propose(f"p{i}", "opportunity", "record_review", "agent:d", {"n": i}, ["ev"]) for i in range(5)]
        self.assertEqual(states, ["PENDING"] * 3 + ["DEFERRED"] * 2)
        # Denying a request does not free capacity for another today.
        book.deny("p0", OWNER)
        self.assertEqual(book.propose("p5", "opportunity", "record_review", "agent:d", {"n": 5}, ["ev"]), "DEFERRED")
        self.assertEqual(book.release_deferred(), [])
        # 2027-01-15 08:00Z + 17h = next UTC day 01:00Z, still inside the 24h decision window.
        now[0] += 17 * 3600
        for pid in ("p1", "p2"):
            book.deny(pid, OWNER)
        released = book.release_deferred()
        self.assertEqual(released, ["p3", "p4", "p5"])
        self.assertTrue(all(book.state(p) == "PENDING" for p in released))

    def test_limit_counts_admitted_requests_not_only_open_ones(self):
        book = ApprovalBook(self.ledger, SECRET.encode())
        for i in range(3):
            book.propose(f"q{i}", "opportunity", "record_review", "agent:d", {"n": i}, ["ev"])
            book.deny(f"q{i}", OWNER)
        self.assertEqual(book.propose("q3", "opportunity", "record_review", "agent:d", {"n": 3}, ["ev"]), "DEFERRED")

    def test_durable_stop_blocks_web_execution(self):
        app = self.app()
        self.seed()
        cookie, csrf, _, _ = self.session(app, "/approvals/p1")
        self.assertTrue(self.post(app, cookie, csrf, "approve").startswith("303"))
        self.ledger.db.execute("CREATE TABLE IF NOT EXISTS job_meta (id INTEGER PRIMARY KEY CHECK(id=1), version INTEGER NOT NULL, stop TEXT NOT NULL)")
        self.ledger.db.execute("INSERT OR REPLACE INTO job_meta VALUES (1,1,'STOP_EXECUTION')")
        self.assertTrue(self.post(app, cookie, csrf, "execute").startswith("403"))
        self.assertEqual(self.ledger.db.execute("SELECT state FROM proposals WHERE id='p1'").fetchone()[0], "APPROVED")

    def test_csp_allows_only_same_origin_forms(self):
        app = self.app()
        self.seed()
        _, _, response, _ = self.session(app)
        self.assertIn("form-action 'self'", response["headers"]["Content-Security-Policy"])
        self.assertNotIn("accounts.google.com", response["headers"]["Content-Security-Policy"])


if __name__ == "__main__":
    unittest.main()
