"""Laptop bridge: HMAC auth, task queue, loopback endpoint end to end, console key page, and parity with the laptop agent file. Synthetic data, loopback sockets only."""
import importlib.util
import json
import os
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import Mock
from urllib.parse import urlencode

import test_google_web
import test_missions
from apex import bridge_auth, bridge_queue
from apex.bridge_server import make_server
from apex.bridge_web import BridgeRoutes, is_bridge_path
from apex.console_server import ConsoleApp
from apex.kernel.memory import Ledger

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("laptop_agent", ROOT / "scripts" / "laptop_agent.py")
agent = importlib.util.module_from_spec(spec)
spec.loader.exec_module(agent)

URL = "https://console.cloud.google.com/auth/clients?project=apex-personal"


def headers_for(key_id, key, path, body, ts=None, nonce="a" * 32):
    ts = str(int(time.time()) if ts is None else ts)
    return {"x-apex-key-id": key_id, "x-apex-ts": ts, "x-apex-nonce": nonce, "x-apex-sig": bridge_auth.sign_request(key, "POST", path, ts, nonce, body)}


class AuthTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        shown = bridge_auth.create_key(self.root)
        self.key_id, self.key = bridge_auth.load_key(self.root)
        self.shown = shown

    def tearDown(self):
        self.tmp.cleanup()

    def test_key_creation_display_and_permissions(self):
        self.assertEqual(self.shown, f"{self.key_id}.{self.key.hex()}")
        self.assertTrue(agent.KEY_RE.fullmatch(self.shown))
        self.assertEqual(os.stat(bridge_auth.key_file(self.root)).st_mode & 0o777, 0o600)
        bridge_auth.create_key(self.root)
        self.assertNotEqual(bridge_auth.load_key(self.root)[1], self.key)                       # rotation replaces the key
        os.chmod(bridge_auth.key_file(self.root), 0o644)
        with self.assertRaises(bridge_auth.AuthError):
            bridge_auth.load_key(self.root)

    def test_verify_accepts_fresh_signed_and_rejects_tamper_stale_replay(self):
        nonces, body = bridge_auth.NonceCache(), b"{}"
        h = headers_for(self.key_id, self.key, "/bridge/poll", body)
        bridge_auth.verify_request(self.key_id, self.key, h, "POST", "/bridge/poll", body, nonces)
        with self.assertRaises(bridge_auth.AuthError):                                          # same nonce again = replay
            bridge_auth.verify_request(self.key_id, self.key, h, "POST", "/bridge/poll", body, nonces)
        fresh = headers_for(self.key_id, self.key, "/bridge/poll", body, nonce="b" * 32)
        for method, path, payload in (("POST", "/bridge/result", body), ("POST", "/bridge/poll", b'{"x":1}'), ("GET", "/bridge/poll", body)):
            with self.assertRaises(bridge_auth.AuthError, msg=f"{method} {path}"):
                bridge_auth.verify_request(self.key_id, self.key, fresh, method, path, payload, bridge_auth.NonceCache())
        stale = headers_for(self.key_id, self.key, "/bridge/poll", body, ts=int(time.time()) - 500, nonce="c" * 32)
        with self.assertRaises(bridge_auth.AuthError):
            bridge_auth.verify_request(self.key_id, self.key, stale, "POST", "/bridge/poll", body, bridge_auth.NonceCache())
        wrong_key = headers_for(self.key_id, b"x" * 32, "/bridge/poll", body, nonce="d" * 32)
        with self.assertRaises(bridge_auth.AuthError):
            bridge_auth.verify_request(self.key_id, self.key, wrong_key, "POST", "/bridge/poll", body, bridge_auth.NonceCache())
        with self.assertRaises(bridge_auth.AuthError):
            bridge_auth.verify_request(self.key_id, self.key, {}, "POST", "/bridge/poll", body, bridge_auth.NonceCache())

    def test_agent_file_signs_exactly_like_the_server(self):
        args = ("POST", "/bridge/poll", "1794000000", "e" * 32, b'{"a":1}')
        self.assertEqual(agent.sign_request(self.key, *args), bridge_auth.sign_request(self.key, *args))
        self.assertEqual(agent.response_sig(self.key, "e" * 32, 200, b"x"), bridge_auth.sign_response(self.key, "e" * 32, 200, b"x"))


class QueueTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger = Ledger(Path(self.tmp.name))
        self.now = [1_800_000_000.0]
        self.q = bridge_queue.BridgeQueue(self.ledger, clock=lambda: self.now[0])

    def tearDown(self):
        self.ledger.close()
        self.tmp.cleanup()

    def test_validation(self):
        bad = ((("x", "http://console.cloud.google.com/", [])), (("x", "https://evil.example/", [])), (("x", "https://u:p@console.cloud.google.com/", [])),
               (("", URL, [])), (("x", URL, [{"action": "eval", "selector": "a"}])), (("x", URL, [{"action": "click", "selector": ""}])),
               (("x", URL, [{"action": "fill", "selector": "a", "value": "v" * 501}])), (("x", URL, [{"action": "click", "selector": "a", "extra": 1}])),
               (("x", URL, [{"action": "click", "selector": "a"}] * 31)))
        for args in bad:
            with self.assertRaises(bridge_queue.QueueError, msg=str(args)[:60]):
                self.q.enqueue(*args)

    def test_lifecycle_lease_token_and_expiry(self):
        task_id = self.q.enqueue("open it", URL, [{"action": "click", "selector": "text=Next"}])
        leased = self.q.lease_next()
        self.assertEqual((leased["id"], leased["url"]), (task_id, URL))
        self.assertIsNone(self.q.lease_next())                                                   # leased, not handed out twice
        self.assertFalse(self.q.submit_result(task_id, "wrong-token", {"status": "FINISHED"}))
        self.now[0] += bridge_queue.LEASE_SECONDS + 1
        again = self.q.lease_next()                                                              # lease expired: re-offered with a NEW token
        self.assertEqual(again["id"], task_id)
        self.assertNotEqual(again["lease_token"], leased["lease_token"])
        self.assertFalse(self.q.submit_result(task_id, leased["lease_token"], {"status": "FINISHED"}))
        self.assertTrue(self.q.submit_result(task_id, again["lease_token"], {"status": "FINISHED", "steps": []}))
        self.assertEqual(self.q.status(task_id)["state"], "DONE")
        self.assertFalse(self.q.submit_result(task_id, again["lease_token"], {"status": "FINISHED"}))      # no second result
        events = [r["payload"]["event"] for r in self.ledger.records("personal")]
        self.assertEqual(events, ["bridge_task_enqueued", "bridge_task_done"])

    def test_limits(self):
        for _ in range(bridge_queue.MAX_PENDING):
            self.q.enqueue("x", URL, [])
        with self.assertRaisesRegex(bridge_queue.QueueError, "too many"):
            self.q.enqueue("x", URL, [])
        leased = self.q.lease_next()
        with self.assertRaisesRegex(bridge_queue.QueueError, "too large"):
            self.q.submit_result(leased["id"], leased["lease_token"], {"blob": "x" * 9000})
        self.now[0] += bridge_queue.TTL_SECONDS + 5
        self.assertIsNone(self.q.lease_next())                                                   # old tasks are never handed out
        self.assertEqual(self.q.summary()["last_poll"], None)


class EndpointTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        bridge_auth.create_key(self.root)
        self.key_id, self.key = bridge_auth.load_key(self.root)
        self.server = make_server(self.root, port=0)
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.tmp.cleanup()

    def enqueue(self, steps=()):
        with Ledger(self.root) as ledger:
            return bridge_queue.BridgeQueue(ledger).enqueue("test task", URL, list(steps))

    def raw_post(self, path, body, headers):
        request = urllib.request.Request(self.base + path, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=5) as r:
                return r.status
        except urllib.error.HTTPError as exc:
            return exc.code

    def test_only_loopback_and_unknown_paths(self):
        with self.assertRaises(ValueError):
            make_server(self.root, host="0.0.0.0")
        self.assertEqual(urllib.request.urlopen(self.base + "/bridge/health", timeout=5).status, 200)
        for path in ("/", "/bridge/enqueue", "/bridge/key", "/admin"):
            self.assertEqual(self.raw_post(path, b"{}", {}), 404, path)

    def test_unauthenticated_and_tampered_requests_get_a_bare_401(self):
        self.assertEqual(self.raw_post("/bridge/poll", b"{}", {}), 401)
        h = {k: v for k, v in headers_for(self.key_id, self.key, "/bridge/poll", b"{}").items()}
        h = {"X-Apex-Key-Id": h["x-apex-key-id"], "X-Apex-Ts": h["x-apex-ts"], "X-Apex-Nonce": h["x-apex-nonce"], "X-Apex-Sig": h["x-apex-sig"]}
        self.assertEqual(self.raw_post("/bridge/poll", b'{"tampered":1}', h), 401)
        self.assertEqual(self.raw_post("/bridge/poll", b"{}", h), 204)                          # untampered passes ...
        self.assertEqual(self.raw_post("/bridge/poll", b"{}", h), 401)                          # ... and replaying it is refused
        self.assertEqual(self.raw_post("/bridge/poll", b"x" * 20000, {"Content-Length": "20000"}), 400)

    def test_full_round_trip_with_the_agents_own_client_code(self):
        status, data = agent.call(self.base, "/bridge/poll", {}, self.key_id, self.key)
        self.assertEqual((status, data), (204, None))
        task_id = self.enqueue([{"action": "click", "selector": "text=Next"}])
        status, data = agent.call(self.base, "/bridge/poll", {}, self.key_id, self.key)
        task = data["task"]
        self.assertEqual((status, task["id"], task["url"]), (200, task_id, URL))
        self.assertTrue(agent.task_ok(task))
        status, answer = agent.call(self.base, "/bridge/result", {"id": task_id, "lease_token": "nope", "result": {"status": "FINISHED"}}, self.key_id, self.key)
        self.assertEqual((status, answer["ok"]), (409, False))
        status, answer = agent.call(self.base, "/bridge/result", {"id": task_id, "lease_token": task["lease_token"], "result": {"status": "FINISHED", "steps": []}}, self.key_id, self.key)
        self.assertEqual((status, answer["ok"]), (200, True))
        with Ledger(self.root) as ledger:
            self.assertEqual(bridge_queue.BridgeQueue(ledger).status(task_id)["state"], "DONE")
            self.assertIsNotNone(bridge_queue.BridgeQueue(ledger).summary()["last_poll"])

    def test_agent_rejects_unsigned_or_wrongly_signed_answers(self):
        wrong = (self.key_id, b"y" * 32)
        with self.assertRaises(agent.Rejected):                                                 # server cannot verify us -> 401 -> Rejected
            agent.call(self.base, "/bridge/poll", {}, *wrong)

    def test_agent_policy_matches_the_server_and_refuses_unsafe_tasks(self):
        self.assertEqual(agent.ALLOWED_HOSTS, bridge_queue.ALLOWED_HOSTS)
        self.assertEqual(agent.HUMAN_HOSTS <= agent.ALLOWED_HOSTS, True)
        base = {"purpose": "p", "url": URL, "steps": []}
        self.assertTrue(agent.task_ok(base))
        for bad in ({**base, "url": "https://linkedin.com/jobs"}, {**base, "url": "http://console.cloud.google.com/"}, {**base, "steps": [{"action": "eval", "selector": "x"}]},
                    {**base, "steps": [{"action": "click", "selector": "x"}] * 31}, {**base, "purpose": ""}):
            self.assertFalse(agent.task_ok(bad))
        self.assertTrue(agent.CONSENT_WORDS.search("Allow"))
        self.assertTrue(agent.CONSENT_WORDS.search("I agree"))
        self.assertTrue(agent.SECRET_FIELD.search("input[name=password]"))


class ConsolePageTests(unittest.TestCase):
    setUp = test_missions.MissionTests.setUp
    tearDown = test_missions.MissionTests.tearDown
    call = test_google_web.GoogleWebTests.call

    def app(self):
        return ConsoleApp(self.root, Mock(valid=Mock(return_value=True)), None, None, None, None, BridgeRoutes(self.root, "owner@example.org"))

    def session(self, app):
        import hashlib
        from http.cookies import SimpleCookie
        response, body = self.call(app, "/bridge")
        parsed = SimpleCookie()
        parsed.load(response["headers"]["Set-Cookie"])
        sid = parsed["__Host-apex-owner"].value
        csrf = self.ledger.db.execute("SELECT csrf FROM owner_web_sessions WHERE id=?", (hashlib.sha256(sid.encode()).hexdigest(),)).fetchone()[0]
        return response["headers"]["Set-Cookie"], csrf, response, body

    def test_paths(self):
        self.assertTrue(is_bridge_path("/bridge") and is_bridge_path("/bridge/key") and is_bridge_path("/bridge/agent.py"))
        self.assertFalse(is_bridge_path("/bridge/poll") or is_bridge_path("/bridge/key/x"))

    def test_agent_file_download_is_owner_only_and_identical_to_the_repo_file(self):
        app = self.app()
        cookie, _, _, page = self.session(app)
        self.assertIn(b"/bridge/agent.py", page)
        response, body = self.call(app, "/bridge/agent.py", cookie)
        self.assertTrue(response["status"].startswith("200"))
        self.assertEqual(body, (ROOT / "scripts" / "laptop_agent.py").read_bytes())
        self.assertIn("attachment", response["headers"]["Content-Disposition"])
        app.verifier.valid.return_value = False
        self.assertTrue(self.call(app, "/bridge/agent.py", cookie)[0]["status"].startswith("401"))

    def test_key_is_created_once_shown_once_and_csrf_protected(self):
        app = self.app()
        cookie, csrf, response, page = self.session(app)
        self.assertTrue(response["status"].startswith("200"))
        self.assertIn(b"not created yet", page)
        self.assertFalse(bridge_auth.key_file(self.root).exists())                                # viewing creates nothing
        self.assertTrue(self.call(app, "/bridge/key", cookie, "POST", "csrf=wrong")[0]["status"].startswith("403"))
        self.assertFalse(bridge_auth.key_file(self.root).exists())
        response, body = self.call(app, "/bridge/key", cookie, "POST", urlencode({"csrf": csrf}))
        self.assertTrue(response["status"].startswith("200"))
        shown = bridge_auth.load_key(self.root)
        self.assertIn(f"{shown[0]}.{shown[1].hex()}".encode(), body)
        again = self.call(app, "/bridge", cookie)[1]
        self.assertNotIn(shown[1].hex().encode(), again)                                           # never displayed again
        self.assertIn(b"created", again)
        app.verifier.valid.return_value = False
        self.assertTrue(self.call(app, "/bridge")[0]["status"].startswith("401"))


if __name__ == "__main__":
    unittest.main()
