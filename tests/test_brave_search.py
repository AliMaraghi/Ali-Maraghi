import json, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "core"))
from apex import brave_search as bs, research, scout_common
from apex.kernel.budget import Budget
from apex.kernel.memory import Ledger

KEY = "BSA" + "x" * 28


def reply(*items):
    return json.dumps({"web": {"results": [{"title": t, "url": u, "description": d} for t, u, d in items]}}).encode()


class Brave(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())

    def test_key_is_private_and_shape_checked(self):
        self.assertIsNone(bs.load_key(self.root))
        with self.assertRaises(ValueError):
            bs.save_key(self.root, "short")
        bs.save_key(self.root, KEY)
        path = self.root / "runtime" / "inbox" / "brave-api-key"
        self.assertEqual((path.stat().st_mode & 0o777, bs.load_key(self.root)), (0o600, KEY))
        path.chmod(0o644)
        self.assertIsNone(bs.load_key(self.root))                       # readable by others: ignored

    def test_query_is_site_filtered_and_stray_domains_are_dropped(self):
        seen = {}
        def get(url, key):
            seen.update(url=url, key=key)
            return reply(("Retinoids", "https://www.nhs.uk/conditions/x/", "Retinoid creams <strong>thin</strong> the skin."),
                         ("Shop", "https://buy-retinol.example.com/", "Best price"), ("Plain", "http://www.gov.uk/x", "not https"))
        out = bs.search(self.root, KEY, "en-gb", "retinol skin", get=get)
        self.assertEqual([(s["domain"], s["extract"]) for s in out], [("www.nhs.uk", "Retinoid creams thin the skin.")])
        self.assertTrue(seen["url"].startswith(bs.ENDPOINT + "?") and "site%3Anhs.uk" in seen["url"] and seen["key"] == KEY)
        self.assertEqual(bs.usage(self.root)["calls"], 1)

    def test_monthly_ceiling_stops_calls(self):
        (self.root / "runtime" / "inbox").mkdir(parents=True)
        month = bs.usage(self.root)["month"]
        (self.root / "runtime" / "inbox" / "brave_usage.json").write_text(json.dumps({month: bs.MONTHLY_CEILING}))
        with self.assertRaises(bs.BraveError):
            bs.search(self.root, KEY, "en-gb", "x", get=lambda url, key: reply())

    def test_research_uses_institutions_only_and_names_domains(self):
        ledger = Ledger(self.root)
        budget = Budget(ledger)
        budget.set_price(scout_common.PROVIDER, scout_common.SKU, 2000, 1.0, "test")
        budget.set_cap(scout_common.POOL, "day", 1000)
        calls = []
        def institutional(region, phrase):
            calls.append(region)
            return [{"title": "T", "url": f"https://x.{region}.example/", "domain": "nhs.uk", "lang": region, "extract": "SPF protects skin."}]
        llm = lambda s, u, m: json.dumps({"answer": "SPF protects skin (nhs.uk).", "used": [1], "missing": ""})
        def boom(url):
            raise AssertionError("Wikipedia must not be used when institutional search is on")
        saved, bs.SPACING_SECONDS = bs.SPACING_SECONDS, 0
        try:
            out = research.run("Does SPF protect skin?", boom, llm, budget, multilingual=False, institutional=institutional)
        finally:
            bs.SPACING_SECONDS = saved
            ledger.close()
        self.assertEqual((out["status"], out["provider"], calls), ("OK", "institutional", ["en-gb", "en-us", "global"]))
        self.assertEqual(out["sources"][0]["domain"], "nhs.uk")


if __name__ == "__main__":
    unittest.main()
