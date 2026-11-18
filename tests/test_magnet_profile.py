import json, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "core"))
from apex import magnet_profile, scout_common, scout_events
from apex.kernel.budget import Budget
from apex.kernel.memory import Ledger


class MagnetProfile(unittest.TestCase):
    def setUp(self):
        self.ledger = Ledger(Path(tempfile.mkdtemp()))
        self.budget = Budget(self.ledger)
        self.budget.set_price(scout_common.PROVIDER, scout_common.SKU, 2000, 1.0, "test")
        self.budget.set_cap(scout_common.POOL, "day", 100)

    def tearDown(self):
        self.ledger.close()

    def test_drafts_come_back_and_invented_numbers_are_dropped(self):
        reply = {"bio": "Tech, coffee and long walks in North London.",
                 "posts": [f"Idea {c}" for c in "abcdefghij"] + ["extra"],
                 "hooks": ["Glad you liked it - where was yours taken?", "I earn 90000 a year", "Ha, thank you!"]}
        out = magnet_profile.generate(lambda s, u, m: json.dumps(reply), self.budget, "I work in tech. I like coffee and walks.")
        self.assertEqual(out["status"], "OK")
        self.assertEqual(len(out["posts"]), 10)
        self.assertEqual(len(out["hooks"]), 2)                    # the one with an invented figure is gone

    def test_no_model_or_empty_notes_gives_no_draft(self):
        self.assertEqual(magnet_profile.generate(None, self.budget, "notes")["status"], "NO_DRAFT")
        self.assertEqual(magnet_profile.generate(None, self.budget, "   ")["status"], "EMPTY_NOTES")

    def test_scout_keeps_a_clean_opener(self):
        ical = (b"BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\nSUMMARY:Wine tasting social\r\nDTSTART:20261120T190000\r\n"
                b"URL:https://www.meetup.com/g/events/1/\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n")
        reply = {"picks": [1], "why": ["Relaxed, easy to talk"], "opener": ["Which one have you liked most so far?"]}
        now = 1795132800.0                                        # 2026-11-19 12:00 UTC
        out = scout_events.run({"meetup_groups": ["g"], "profile": "p"}, lambda url: ical,
                               lambda s, u, m: json.dumps(reply), self.budget, now)
        self.assertEqual(out["selection"], "model")
        self.assertEqual(out["picked"][0]["opener"], "Which one have you liked most so far?")


if __name__ == "__main__":
    unittest.main()
