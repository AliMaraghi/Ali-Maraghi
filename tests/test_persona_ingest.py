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


class ChatIngestTests(unittest.TestCase):
    ANDROID = ("12/03/2024, 21:15 - Messages and calls are end-to-end encrypted.\n"
               "12/03/2024, 21:15 - Ali M: are you still coming on friday because I booked the table for eight and they want numbers\n"
               "12/03/2024, 21:16 - Sara: yes!! and this private reply from someone else must never be read or stored anywhere\n"
               "12/03/2024, 21:17 - Ali M: great\n12/03/2024, 21:17 - Ali M: I will bring the tickets\nand the second line of my own message continues here too\n"
               "12/03/2024, 21:18 - Ali M: <Media omitted>\n"
               "13/03/2024, 09:00 - Ali M: send the deposit to 12345678 before noon please or they will give the table away to others\n")
    IOS = "[05/01/2023, 18:02:11] Ali M: سلام امشب دیرتر می‌رسم چون جلسه طول کشید و باید یک گزارش دیگر هم بفرستم بعد راه می‌افتم\n[05/01/2023, 18:03:00] Reza: باشه\n"

    def test_only_owner_lines_from_whatsapp_and_meta(self):
        import zipfile
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "chats"
            folder.mkdir()
            (folder / "WhatsApp Chat with Sara.txt").write_text(self.ANDROID, encoding="utf-8")
            with zipfile.ZipFile(folder / "export.zip", "w") as archive:
                archive.writestr("_chat.txt", self.IOS)
            meta = {"participants": [{"name": "Ali M"}, {"name": "Tom"}], "messages": [
                {"sender_name": "Ali M", "timestamp_ms": 1_700_000_000_000, "content": "I think we should leave earlier than planned because the trains are a mess on sundays"},
                {"sender_name": "Tom", "timestamp_ms": 1_700_000_100_000, "content": "another person's message that must be skipped completely and never sampled"},
                {"sender_name": "Ali M", "timestamp_ms": 1_300_000_000_000, "content": "this one is from 2011 and is older than the cut-off so it is ignored entirely here"}]}
            (folder / "message_1.json").write_text(json.dumps(meta), encoding="utf-8")
            stats, samples = persona_ingest.analyse_chats(folder, {"Ali M"}, 2012, 60)
            joined = " ".join(samples)
            self.assertEqual(stats["chat_files_with_your_messages"], 3)
            self.assertEqual(stats["by_language"], {"en": 4, "fa": 1})
            self.assertIn("booked the table", joined)
            self.assertIn("second line of my own message", joined)             # multi-line owner message kept together
            self.assertIn("trains are a mess", joined)
            self.assertTrue(any("جلسه" in sample for sample in samples))
            for forbidden in ("private reply", "another person", "12345678", "Media omitted", "2011", "باشه", "end-to-end"):
                self.assertNotIn(forbidden, joined)
            root = Path(tmp) / "root"
            persona_ingest.write_chat_outputs(root, stats, samples)
            self.assertEqual(len(persona_twin.load_profile(root, "chat").samples), len(samples))
            self.assertEqual(persona_twin.load_profile(root).samples, ())       # chat samples do not leak into the written register
            self.assertNotIn("table", json.dumps(stats))

    def test_owner_name_is_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                persona_ingest.analyse_chats(Path(tmp), set())


if __name__ == "__main__":
    unittest.main()
