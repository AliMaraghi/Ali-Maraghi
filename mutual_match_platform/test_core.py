"""Mutual-match platform core (brutal-honesty directive, 2026-11-15, Mission 2). All
synthetic fixtures - no real user data."""
import tempfile
import unittest
from pathlib import Path

from core import MutualMatchPlatform, PlatformError


class PlatformBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.tmp.name) / "platform.sqlite3")
        self.now = [1_800_000_000.0]
        self.platform = MutualMatchPlatform(self.db_path, now=lambda: self.now[0], daily_like_limit=3)

    def tearDown(self):
        self.tmp.cleanup()

    def make_profile(self, user_id, age=28, sensitive=None):
        self.platform.create_profile(user_id, f"User {user_id}", age, 18, 99,
                                     sensitive or {"gender": "f", "orientation": "straight"})


class ProfileAndDeletionTests(PlatformBase):
    def test_under_18_profile_refused(self):
        with self.assertRaises(PlatformError):
            self.platform.create_profile("u1", "Minor", 17, 18, 99, {})

    def test_sensitive_data_stored_separately_and_encrypted(self):
        self.make_profile("u1", sensitive={"gender": "f", "orientation": "straight"})
        raw = self.platform.db.execute("SELECT encrypted_blob FROM sensitive_profile_data WHERE user_id='u1'").fetchone()[0]
        self.assertNotIn(b"straight", raw)      # not plaintext in the DB
        public_row = self.platform.db.execute("SELECT * FROM profiles WHERE user_id='u1'").fetchone()
        self.assertNotIn("gender", str(public_row))   # public table never carries sensitive fields

    def test_full_deletion_path(self):
        self.make_profile("u1"); self.make_profile("u2")
        self.platform.like("u1", "u2"); self.platform.like("u2", "u1")
        self.platform.send_message("u1", "u2", "hi")
        self.platform.block("u2", "u1")
        self.platform.report("u2", "u1", "spam")

        counts = self.platform.delete_account("u1")
        self.assertGreater(sum(counts.values()), 0)
        self.assertIsNone(self.platform.db.execute("SELECT 1 FROM profiles WHERE user_id='u1'").fetchone())
        self.assertIsNone(self.platform.db.execute("SELECT 1 FROM sensitive_profile_data WHERE user_id='u1'").fetchone())
        self.assertIsNone(self.platform.db.execute("SELECT 1 FROM likes WHERE liker_id='u1' OR liked_id='u1'").fetchone())
        self.assertIsNone(self.platform.db.execute("SELECT 1 FROM messages WHERE sender_id='u1' OR recipient_id='u1'").fetchone())
        self.assertIsNone(self.platform.db.execute("SELECT 1 FROM blocks WHERE blocker_id='u1' OR blocked_id='u1'").fetchone())
        self.assertIsNone(self.platform.db.execute("SELECT 1 FROM reports WHERE reporter_id='u1' OR reported_id='u1'").fetchone())


class MutualMatchMessagingTests(PlatformBase):
    def test_no_message_without_mutual_match(self):
        """The mission's own required test: without a mutual match, no message sends."""
        self.make_profile("u1"); self.make_profile("u2")
        with self.assertRaises(PlatformError) as ctx:
            self.platform.send_message("u1", "u2", "hey")
        self.assertEqual(str(ctx.exception), "NO_MUTUAL_MATCH")

        self.platform.like("u1", "u2")      # one-sided only
        with self.assertRaises(PlatformError) as ctx:
            self.platform.send_message("u1", "u2", "hey")
        self.assertEqual(str(ctx.exception), "NO_MUTUAL_MATCH")

        matched = self.platform.like("u2", "u1")   # now mutual
        self.assertTrue(matched)
        mid = self.platform.send_message("u1", "u2", "hey")
        self.assertIsInstance(mid, int)

    def test_like_returns_match_boolean_correctly(self):
        self.make_profile("u1"); self.make_profile("u2")
        self.assertFalse(self.platform.like("u1", "u2"))
        self.assertTrue(self.platform.like("u2", "u1"))

    def test_cannot_like_self(self):
        self.make_profile("u1")
        with self.assertRaises(PlatformError):
            self.platform.like("u1", "u1")

    def test_daily_like_rate_limit(self):
        self.make_profile("u1")
        for i in range(3):
            self.make_profile(f"target{i}")
            self.platform.like("u1", f"target{i}")
        self.make_profile("target3")
        with self.assertRaises(PlatformError) as ctx:
            self.platform.like("u1", "target3")
        self.assertIn("DAILY_LIKE_LIMIT_EXCEEDED", str(ctx.exception))

    def test_rate_limit_resets_the_next_day(self):
        self.make_profile("u1")
        for i in range(3):
            self.make_profile(f"target{i}")
            self.platform.like("u1", f"target{i}")
        self.now[0] += 86400 + 1
        self.make_profile("target3")
        self.platform.like("u1", "target3")   # does not raise

    def test_visible_profiles_only_shows_mutual_matches(self):
        self.make_profile("u1"); self.make_profile("u2"); self.make_profile("u3")
        self.platform.like("u1", "u2"); self.platform.like("u1", "u3")   # one-sided
        self.platform.like("u2", "u1")                                   # mutual with u2 only
        self.assertEqual(self.platform.visible_profiles_for("u1"), ["u2"])


class SafetyTests(PlatformBase):
    def test_blocked_pair_cannot_like_or_message(self):
        self.make_profile("u1"); self.make_profile("u2")
        self.platform.like("u1", "u2"); self.platform.like("u2", "u1")
        self.platform.block("u2", "u1")
        with self.assertRaises(PlatformError):
            self.platform.like("u1", "u2")
        with self.assertRaises(PlatformError):
            self.platform.send_message("u1", "u2", "hi")

    def test_report_blocks_immediately(self):
        self.make_profile("u1"); self.make_profile("u2")
        self.platform.report("u2", "u1", "harassment")
        self.assertTrue(self.platform._is_blocked("u2", "u1"))

    def test_review_sla_24h(self):
        self.make_profile("u1"); self.make_profile("u2")
        rid = self.platform.report("u2", "u1", "harassment")
        self.assertEqual(self.platform.review_overdue(), [])     # not overdue yet
        self.now[0] += 24 * 3600 + 1
        overdue = self.platform.review_overdue()
        self.assertEqual(len(overdue), 1)
        self.assertEqual(overdue[0]["id"], rid)
        self.platform.resolve_report(rid, "account suspended")
        self.assertEqual(self.platform.review_overdue(), [])     # resolved, no longer overdue


if __name__ == "__main__":
    unittest.main()
