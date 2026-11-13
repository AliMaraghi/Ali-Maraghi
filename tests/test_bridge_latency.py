"""Headless latency benchmark for the laptop bridge round trip (enqueue -> poll -> lease -> result).

This is a TEST FIXTURE, not a production script: the "automatic y" here is the same pattern test_bridge.py already uses
(agent.call() driven directly, no real stdin/keyboard), run against the real bridge_server/bridge_queue code over a real
loopback socket. It never touches scripts/laptop_agent.py's interactive Console (no stdin is simulated or bypassed on a
real agent process). Purely local timing; no network, no laptop, no production deployment.
"""
import importlib.util
import tempfile
import threading
import time
import unittest
from pathlib import Path

from apex import bridge_auth, bridge_queue
from apex.bridge_server import make_server
from apex.kernel.memory import Ledger

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("laptop_agent", ROOT / "scripts" / "laptop_agent.py")
agent = importlib.util.module_from_spec(spec)
spec.loader.exec_module(agent)

URL = "https://console.cloud.google.com/auth/clients?project=apex-personal"
ROUND_TRIPS = 20
LATENCY_BUDGET_SECONDS = 2.0


class HeadlessLatencyTests(unittest.TestCase):
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

    def enqueue(self):
        with Ledger(self.root) as ledger:
            return bridge_queue.BridgeQueue(ledger).enqueue("latency test", URL, [])

    def test_single_round_trip_completes_well_under_two_seconds(self):
        task_id = self.enqueue()
        start = time.monotonic()
        status, data = agent.call(self.base, "/bridge/poll", {}, self.key_id, self.key)
        task = data["task"]
        # Automatic "y" is this test's own code path (no Console, no production agent process); it proves the
        # SERVER side has no inherent delay. It never stands in for the owner's real approval on a real laptop.
        status, answer = agent.call(self.base, "/bridge/result", {"id": task_id, "lease_token": task["lease_token"],
                                                                    "result": {"status": "FINISHED", "steps": []}}, self.key_id, self.key)
        elapsed = time.monotonic() - start
        self.assertEqual((status, answer["ok"]), (200, True))
        self.assertLess(elapsed, LATENCY_BUDGET_SECONDS, f"round trip took {elapsed:.3f}s")

    def test_sustained_round_trips_stay_within_budget(self):
        durations = []
        for _ in range(ROUND_TRIPS):
            task_id = self.enqueue()
            start = time.monotonic()
            _, data = agent.call(self.base, "/bridge/poll", {}, self.key_id, self.key)
            task = data["task"]
            agent.call(self.base, "/bridge/result", {"id": task_id, "lease_token": task["lease_token"], "result": {"status": "FINISHED", "steps": []}},
                      self.key_id, self.key)
            durations.append(time.monotonic() - start)
        self.assertLess(max(durations), LATENCY_BUDGET_SECONDS, f"slowest of {ROUND_TRIPS} round trips: {max(durations):.3f}s")
        self.assertLess(sum(durations) / len(durations), LATENCY_BUDGET_SECONDS / 4)


if __name__ == "__main__":
    unittest.main()
