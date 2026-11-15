"""Observability (mission 2026-11-15, Phase 3). Gate P3: run the recorder twice, status
reflects runs_total=2 and uptime_days >= 0 honestly (no fabricated baseline)."""
import tempfile
import unittest
from pathlib import Path

from apex.kernel import observability as obs


class ObservabilityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "observability.jsonl"

    def tearDown(self):
        self.tmp.cleanup()

    def test_empty_file_reports_honest_zero_not_fabricated_uptime(self):
        s = obs.status(self.path)
        self.assertEqual(s, {"uptime_days": 0.0, "last_run": None, "runs_total": 0,
                              "runs_succeeded": 0, "runs_failed": 0})

    def test_run_twice_runs_total_is_two(self):
        obs.record_run(self.path, ["A-1", "A-10"], True, 12.5, now=1_800_000_000.0)
        obs.record_run(self.path, ["A-1", "A-10"], True, 8.2, now=1_800_086_400.0)   # +1 day
        s = obs.status(self.path, now=1_800_086_400.0)
        self.assertEqual(s["runs_total"], 2)
        self.assertEqual(s["runs_succeeded"], 2)
        self.assertEqual(s["runs_failed"], 0)
        self.assertGreaterEqual(s["uptime_days"], 0)
        self.assertAlmostEqual(s["uptime_days"], 1.0, places=3)

    def test_failed_run_is_counted_separately(self):
        obs.record_run(self.path, [], True, 1.0, now=1_800_000_000.0)
        obs.record_run(self.path, [], False, 1.0, now=1_800_000_010.0)
        s = obs.status(self.path, now=1_800_000_010.0)
        self.assertEqual(s["runs_total"], 2)
        self.assertEqual(s["runs_succeeded"], 1)
        self.assertEqual(s["runs_failed"], 1)

    def test_last_run_timestamp_is_the_most_recent_not_the_first(self):
        obs.record_run(self.path, [], True, 1.0, now=1_800_000_000.0)
        obs.record_run(self.path, [], True, 1.0, now=1_800_000_500.0)
        s = obs.status(self.path, now=1_800_000_500.0)
        self.assertEqual(s["last_run"], "2027-01-15T08:08:20Z")


if __name__ == "__main__":
    unittest.main()
