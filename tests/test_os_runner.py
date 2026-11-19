import sys, tempfile, unittest
from pathlib import Path
R = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R / "core")); sys.path.insert(0, str(R / "scripts"))
from apex import priority, trend_scout

RSS = b"""<rss xmlns:ht="https://trends.google.com/trending/rss"><channel>
<item><title>Budget 2026</title><ht:approx_traffic>200K+</ht:approx_traffic><ht:news_item><ht:news_item_title>Chancellor sets out plan</ht:news_item_title></ht:news_item></item>
<item><title>Small thing</title><ht:approx_traffic>500+</ht:approx_traffic></item></channel></rss>"""


class Maths(unittest.TestCase):
    def test_posterior_and_discount(self):
        self.assertEqual(priority.posterior(0, 0), 0.5)
        self.assertAlmostEqual(priority.posterior(8, 0), 0.9)
        self.assertEqual(priority.discount(48), 0.5)
        self.assertEqual(priority.surprise(None, 100), 10.0)
        self.assertEqual(priority.surprise(50, 100), 0.0)
        self.assertEqual(priority.surprise(300, 100), 2.0)
        self.assertEqual(priority.ucb(0, 0, 5), float("inf"))
        self.assertGreater(priority.ucb(0, 1, 100), priority.ucb(0, 50, 100))


class Trends(unittest.TestCase):
    def test_scan_ranks_and_records_failures(self):
        def fetch(url):
            if "geo=DE" in url:
                raise RuntimeError("down")
            return RSS
        out = trend_scout.scan(fetch, ["GB", "US", "DE"])
        self.assertEqual(out["feeds_failed"], ["DE:RuntimeError"])
        self.assertEqual(out["top"][0]["term"], "Budget 2026")
        self.assertEqual(out["top"][0]["geos"], ["GB", "US"])
        self.assertEqual(out["top"][0]["traffic"], 400000)

    def test_draft_rejects_junk_and_accepts_json(self):
        t = {"term": "x", "lang": "en", "news": []}
        self.assertIsNone(trend_scout.draft(lambda s, u, m: "sorry", t))
        d = trend_scout.draft(lambda s, u, m: '{"hook":"h","beats":["a","b"],"angle":"story","platform":"tiktok"}', t)
        self.assertEqual(d["state"], "DRAFT_NEEDS_OWNER")


class Cycle(unittest.TestCase):
    def test_real_cycle_on_empty_ledger(self):
        import apex_os_runner
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root / "runtime").mkdir(mode=0o700)
            out = apex_os_runner.cycle(root, now=1795000000.0, fetch=lambda u: RSS, llm=None, run_scouts=False)
            states = {a["agent_id"]: a["state"] for a in out["agents"]}
            self.assertGreaterEqual(len(states), 16)
            self.assertEqual(states["A-15"], "BLOCKED_MISSING_INPUT")
            self.assertEqual(states["A-18"], "NOT_BUILT")
            self.assertIn("trends:OK", [a["task"] + ":" + a["result"] for a in out["actions"]])
            self.assertIn("content_drafts:NO_MODEL", [a["task"] + ":" + a["result"] for a in out["actions"]])
            from apex import scout_common
            self.assertEqual(scout_common.latest(root, "os")["event"], "os_cycle")


if __name__ == "__main__":
    unittest.main()
