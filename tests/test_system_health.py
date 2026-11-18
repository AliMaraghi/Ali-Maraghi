import json, sys, tempfile, time, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "core"))
from apex import scout_common, scout_events, system_health
from apex.agent_loop import Toolbox, ToolError, record_briefing, TOOLS
from apex.kernel.memory import Ledger


class Health(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.now = time.time()

    def test_nothing_recorded_is_red_not_green(self):
        with Ledger(self.root):
            pass
        out = system_health.status(self.root, self.now, probe=lambda: (False, "ConnectionRefusedError"))
        self.assertFalse(out["ok"])
        self.assertTrue(out["checks"]["database"]["ok"])
        self.assertEqual([out["checks"][k]["detail"] for k in ("event_scout", "wealth_scout", "agent_loop")], ["never run"] * 3)

    def test_recent_runs_are_green_and_a_failed_briefing_is_red(self):
        with Ledger(self.root) as ledger:
            scout_common.record(ledger, "events", {"picked": []}, self.now - 60)
            scout_common.record(ledger, "wealth", {"alert": {}}, self.now - 7 * 3600)
            record_briefing(ledger, "g", {"run_id": "r", "status": "MAX_STEPS_REACHED", "report": "x", "trace": [], "proposals": []}, self.now - 60)
        checks = system_health.status(self.root, self.now, probe=lambda: (True, "m"))["checks"]
        self.assertTrue(checks["local_ai"]["ok"] and checks["event_scout"]["ok"])
        self.assertEqual(checks["wealth_scout"]["detail"], "overdue")
        self.assertEqual((checks["agent_loop"]["ok"], checks["agent_loop"]["detail"]), (False, "last run: MAX_STEPS_REACHED"))

    def test_mission_prefers_today_keeps_scout_opener_and_expires(self):
        day = time.strftime("%Y-%m-%d", time.gmtime(self.now + 3 * 3600))
        events = {"picked": [{"title": "Later", "start": "2099-01-01 19:00"},
                             {"title": "Tonight", "start": time.strftime("%Y-%m-%d %H:%M", time.gmtime(self.now + 3 * 3600)), "opener": "What brought you here?"}]}
        picked = scout_events.pick_mission(events, None, None, self.now)
        if day == time.strftime("%Y-%m-%d", time.gmtime(self.now)):
            self.assertEqual((picked["event"]["title"], picked["ice_breaker"], picked["line_source"]), ("Tonight", "What brought you here?", "scout"))
        self.assertEqual(scout_events.pick_mission({"picked": [{"title": "Old", "start": "2020-01-01 10:00"}]}, None, None, self.now)["status"], "NO_EVENT_AHEAD")
        with Ledger(self.root) as ledger:
            scout_common.record(ledger, "mission", {"event": {"title": "Old", "start": "2020-01-01 10:00"}, "ice_breaker": "x"}, self.now)
        self.assertIsNone(system_health.mission(self.root, self.now))

    def test_briefing_agent_can_read_the_scouts(self):
        self.assertIn("read_scouts", TOOLS)
        with Ledger(self.root) as ledger:
            pass
        with self.assertRaises(ToolError):
            Toolbox(root=self.root).read_scouts()
        with Ledger(self.root) as ledger:
            scout_common.record(ledger, "events", {"picked": [{"title": "Wine night", "start": "2026-11-20 19:00", "opener": "hi"}]}, self.now)
            scout_common.record(ledger, "wealth", {"job_status": "NEEDS_REED_KEY", "alert": {"headline": "Rates held"}}, self.now)
        seen = Toolbox(root=self.root).read_scouts()
        self.assertEqual((seen["events"][0]["title"], seen["job"], seen["money_headline"]["headline"]), ("Wine night", "NEEDS_REED_KEY", "Rates held"))


if __name__ == "__main__":
    unittest.main()
