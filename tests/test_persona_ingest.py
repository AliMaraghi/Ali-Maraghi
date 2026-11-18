"""Offline test: voice samples come only from mail the owner sent, with quotes and private details removed."""
import json
import tempfile
import unittest
from pathlib import Path

from apex import persona_ingest, persona_twin

BODY = ("Hi Sam,\n\nI went through the supplier list again this morning and two of the entries are out of date, so I have asked "
        "for fresh certificates before we renew anything.\n\nThe other thing is the Friday meeting, which I would rather move to "
        "the afternoon because the morning is already full and nobody will concentrate.\n\nKind regards,\nAli\n\n"
        "On Mon, 3 Mar 2025 at 10:00, Sam wrote:\n> this quoted line with a secret plan must never be kept as a sample at all\n")


def msg(sender, date, body, extra=""):
    return f"From x@y Mon Jan  1 00:00:00 2024\nFrom: {sender}\nTo: s@example.com\nDate: {date}\nSubject: t\n{extra}Content-Type: text/plain; charset=utf-8\n\n{body}\n\n"


class IngestTests(unittest.TestCase):
    def test_only_owner_sent_words_are_used(self):
        with tempfile.TemporaryDirectory() as tmp:
            box = Path(tmp) / "mail.mbox"
            box.write_text(
                msg("Ali <me@example.com>", "Mon, 03 Mar 2025 12:00:00 +0000", BODY)
                + msg("Sam <sam@example.com>", "Mon, 03 Mar 2025 13:00:00 +0000", "A long message from somebody else that should never be used as the owner's voice at all, ever, in any sample.")
                + msg("me@example.com", "Sat, 01 Jan 2011 12:00:00 +0000", "This one is older than the cut-off year and has more than fifteen words in it so it would otherwise qualify.")
                + msg("me@example.com", "Tue, 04 Mar 2025 12:00:00 +0000", "Please pay the invoice into account 12345678 today because the supplier has been waiting for more than two weeks now.")
                + msg("me@example.com", "Wed, 05 Mar 2025 12:00:00 +0000", "The new starter at Acme Widgets begins on Monday and I have arranged a desk, a laptop and the building pass for her.")
                + msg("me@example.com", "Thu, 06 Mar 2025 12:00:00 +0000", "سلام\n\nامروز فهرست تامین کننده ها را دوباره نگاه کردم و دو مورد قدیمی بود پس گواهی تازه خواستم تا بعد تصمیم بگیریم و جلسه را هم عصر بگذاریم.\n\nبا تشکر", ""),
                encoding="utf-8")
            stats, samples = persona_ingest.analyse(box, {"me@example.com"}, 2012, 60, ("Acme Widgets",))
            joined = " ".join(samples)
            self.assertEqual((stats["messages_in_archive"], stats["sent_by_owner_used"], stats["not_from_owner"]), (6, 4, 1))
            self.assertEqual(stats["by_language"], {"en": 3, "fa": 1})
            self.assertEqual(stats["by_year"], {2025: 4})
            self.assertIn(["hi", 1], [list(g) for g in stats["greetings"]])
            self.assertIn(["kind regards", 1], [list(g) for g in stats["sign_offs"]])
            self.assertIn("supplier list", joined)
            for forbidden in ("secret plan", "somebody else", "12345678", "Acme", "Kind regards", "cut-off"):
                self.assertNotIn(forbidden, joined)
            root = Path(tmp) / "root"
            persona_ingest.write_outputs(root, stats, samples)
            self.assertEqual((root / "runtime" / "inbox" / "persona_samples.md").stat().st_mode & 0o777, 0o600)
            profile = persona_twin.load_profile(root)
            self.assertEqual(len(profile.samples), len(samples))
            self.assertNotIn("supplier", json.dumps(stats))            # stats carry no message content

    def test_owner_address_is_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            box = Path(tmp) / "m.mbox"
            box.write_text("")
            with self.assertRaises(ValueError):
                persona_ingest.analyse(box, set())


if __name__ == "__main__":
    unittest.main()
