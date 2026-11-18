import json, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "core"))
from apex import ghostwriter, scout_adult_events
from apex.sources import public_http

NOW = 1795132800.0                                            # 2026-11-19 12:00 UTC


def page(items):
    data = {"@type": "ItemList", "itemListElement": [{"@type": "ListItem", "item": i} for i in items]}
    return b'<html><script type="application/ld+json">' + json.dumps(data).encode() + b"</script></html>"


def event(name, start, street="5 Devonshire Square, London EC2M 4YE, UK", url="https://events.humanitix.com/a-b"):
    return {"@type": "Event", "name": name, "startDate": start, "url": url,
            "location": {"name": "Venue", "address": {"streetAddress": street}}}


class AdultScout(unittest.TestCase):
    def test_keeps_upcoming_london_events_only(self):
        raw = page([event("Feeld Social", "2026-12-04T18:30:00+0000"),
                    event("Past", "2026-11-01T18:30:00+0000", url="https://events.humanitix.com/past"),
                    event("NYC", "2026-12-05T18:30:00+0000", street="1 Main St, New York", url="https://events.humanitix.com/nyc"),
                    event("Bad link", "2026-12-06T18:30:00+0000", url="https://evil.example/x")])
        out = scout_adult_events.run({}, lambda url: raw, NOW)
        self.assertEqual([e["title"] for e in out["picked"]], ["Feeld Social"])
        self.assertEqual(out["picked"][0]["matched"], ["social"])

    def test_unreachable_host_is_reported_not_fatal(self):
        def boom(url):
            raise RuntimeError("down")
        out = scout_adult_events.run({"adult_event_hosts": ["feeldco"]}, boom, NOW)
        self.assertEqual((out["status"], out["feeds_failed"]), ("NO_EVENTS", ["feeldco:RuntimeError"]))

    def test_only_the_host_page_path_is_allowed(self):
        public_http.validate("https://events.humanitix.com/host/feeldco")
        for bad in ("https://events.humanitix.com/host/feeldco?x=1", "https://events.humanitix.com/checkout/a",
                    "https://events.humanitix.com/host/a/b"):
            with self.assertRaises(public_http.SourceError):
                public_http.validate(bad)


class Ghostwriter(unittest.TestCase):
    def test_voice_sample_is_private_bounded_and_used(self):
        root = Path(tempfile.mkdtemp())
        self.assertEqual(ghostwriter.prompt(root, "hi")[2], False)
        kept = ghostwriter.save_voice(root, "hey you, long day?\nmy number 07123456789\nsee https://x.example\nhaha fair enough")
        self.assertEqual(kept, 2)
        self.assertEqual(ghostwriter.voice_path(root).stat().st_mode & 0o777, 0o600)
        system, user, used = ghostwriter.prompt(root, "I love climbing")
        self.assertTrue(used and "OWNER SAMPLES" in user and "07123456789" not in user and "typing style" in system)
        with self.assertRaises(ValueError):
            ghostwriter.save_voice(root, "   ")


if __name__ == "__main__":
    unittest.main()
