import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "core"))
from apex import scout_common, scout_events


def ical(title):
    return ("BEGIN:VCALENDAR\nBEGIN:VEVENT\nSUMMARY:%s\nDTSTART:20261120T190000Z\nURL:https://www.meetup.com/g/events/1/\nEND:VEVENT\nEND:VCALENDAR\n" % title)


class Exclude(unittest.TestCase):
    def test_business_networking_is_dropped_and_party_kept(self):
        feeds = {"a": ical("Property, Landlords & Business Owners - Business Networking Event"), "b": ical("Rooftop gala evening")}
        cfg = {**scout_common.DEFAULT_CONFIG, "meetup_groups": ["a", "b"]}
        out = scout_events.run(cfg, lambda url: feeds[url.split("/")[3]].encode(), None, None, 1795000000.0)
        self.assertEqual([e["title"] for e in out["picked"]], ["Rooftop gala evening"])
        self.assertEqual(out["considered"], 1)


if __name__ == "__main__":
    unittest.main()
