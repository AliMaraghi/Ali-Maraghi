import json, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "core"))
from apex import research, scout_common
from apex.kernel.budget import Budget
from apex.kernel.memory import Ledger
from apex.sources import public_http


def wiki(lang, title, extract):
    return json.dumps({"query": {"pages": {"1": {"index": 1, "title": title, "extract": extract,
                                                 "fullurl": f"https://{lang}.wikipedia.org/wiki/{title}"}}}}).encode()


class Research(unittest.TestCase):
    def setUp(self):
        self.ledger = Ledger(Path(tempfile.mkdtemp()))
        self.budget = Budget(self.ledger)
        self.budget.set_price(scout_common.PROVIDER, scout_common.SKU, 2000, 1.0, "test")
        self.budget.set_cap(scout_common.POOL, "day", 1000)
        self.fetch = lambda url: wiki(url.split("//")[1][:2], "Retinol", "Retinol is a form of vitamin A used in skin care since 1971.")

    def tearDown(self):
        self.ledger.close()

    def llm(self, synth):
        return lambda system, user, tokens: json.dumps({"en": "retinol", "fa": "رتینول", "fr": "rétinol", "de": "Retinol"} if "search phrase" in system else synth)

    def test_sourced_answer_lists_every_url(self):
        out = research.run("What is retinol?", self.fetch, self.llm({"answer": "Retinol is a form of vitamin A used in skin care since 1971.", "used": [1], "missing": ""}), self.budget)
        self.assertEqual((out["status"], out["used"], len(out["sources"])), ("OK", [1], 4))
        self.assertEqual({s["lang"] for s in out["sources"]}, {"en", "fa", "fr", "de"})

    def test_invented_figure_or_uncited_answer_is_discarded_but_sources_stay(self):
        for bad in ({"answer": "Use 2.5 percent retinol.", "used": [1]}, {"answer": "Retinol is vitamin A.", "used": []}):
            out = research.run("What is retinol?", self.fetch, self.llm(bad), self.budget)
            self.assertEqual((out["status"], out["answer"]), ("SOURCES_ONLY", ""))
            self.assertTrue(out["missing"] and len(out["sources"]) == 4)

    def test_nothing_found_says_so_and_only_the_api_path_is_allowed(self):
        out = research.run("zzzz qqqq", lambda url: b'{"batchcomplete": ""}', self.llm({}), self.budget, multilingual=False)
        self.assertEqual((out["status"], out["sources"]), ("NO_SOURCES", []))
        self.assertEqual(research.run("a", None, None, None)["status"], "BAD_REQUEST")
        public_http.validate(research.search_url("fa", "رتینول"))
        with self.assertRaises(public_http.SourceError):
            public_http.validate("https://en.wikipedia.org/wiki/Special:UserLogin")


if __name__ == "__main__":
    unittest.main()
