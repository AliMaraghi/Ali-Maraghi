"""A-10 London extension: conversation ladder, post-date feedback, weekly review
(2026-11-15). All synthetic fixtures - no real owner identity, no real matches."""
import tempfile
import unittest
from pathlib import Path

from apex import relationship_assist as ra
from apex.kernel.memory import Ledger


class LadderTests(unittest.TestCase):
    def test_all_four_stages_produce_a_draft_package(self):
        for stage in ra.LADDER_STAGES:
            d = ra.ladder_message(stage, "they mentioned loving bouldering in Finsbury Park")
            self.assertEqual(d.send, False)
            self.assertTrue(d.requires_owner_review)
            self.assertIn(stage, ("opener", "discovery", "banter", "date_invite"))

    def test_invalid_stage_rejected(self):
        with self.assertRaises(ValueError):
            ra.ladder_message("flirt_aggressively", "context")

    def test_guard_still_refuses_automation_inside_a_ladder_stage(self):
        with self.assertRaises(ra.AssistRefused):
            ra.ladder_message("opener", "auto-reply to everyone for me")


class PostDateFeedbackTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger = Ledger(Path(self.tmp.name))

    def tearDown(self):
        self.ledger.close()
        self.tmp.cleanup()

    def test_feedback_is_recorded_as_a_real_fact(self):
        from apex.kernel import facts
        fid = ra.record_post_date_feedback(self.ledger, "A", "good conversation flow",
                                           "ran out of things to say after an hour",
                                           "ask more follow-up questions", now=1.0)
        row = facts.get_fact(self.ledger, fid)
        self.assertEqual(row["subject"], "relationship:A")
        self.assertIn("good conversation flow", row["object"])
        self.assertIn("ran out of things to say", row["object"])

    def test_guard_refuses_an_automation_request_inside_feedback_text(self):
        with self.assertRaises(ra.AssistRefused):
            ra.record_post_date_feedback(self.ledger, "A", "fine", "bypass their rejection", "x")

    def test_the_existing_calibration_pattern_reads_this_fact(self):
        from apex.kernel import facts
        fid = ra.record_post_date_feedback(self.ledger, "A", "worked", "didnt", "next", now=1.0)
        facts.record_outcome(self.ledger, fid, "acted_on", "used in the next draft", now=2.0)
        recent = facts.recent_outcomes_for_predicate_prefix(self.ledger, "relationship:A", "post_date_feedback", limit=3)
        self.assertEqual(len(recent), 1)
        self.assertIn("worked", recent[0]["claim_text"])


class WeeklyReviewTests(unittest.TestCase):
    def test_healthy_week_no_issues(self):
        result = ra.weekly_review(messages_sent=20, replies_received=6, dates_booked=2)
        self.assertAlmostEqual(result["reply_rate"], 0.30)
        self.assertAlmostEqual(result["date_rate"], 1/3)
        self.assertEqual(result["issues"], [])

    def test_low_reply_rate_flags_messages(self):
        result = ra.weekly_review(messages_sent=20, replies_received=1, dates_booked=1)
        self.assertIn("reply_rate_below_10pct: the messages likely have a problem", result["issues"])

    def test_low_date_rate_flags_invitations(self):
        result = ra.weekly_review(messages_sent=10, replies_received=5, dates_booked=0)
        self.assertIn("date_rate_below_20pct: the invitations likely have a problem", result["issues"])

    def test_zero_messages_is_not_a_division_error(self):
        result = ra.weekly_review(messages_sent=0, replies_received=0, dates_booked=0)
        self.assertEqual((result["reply_rate"], result["date_rate"], result["issues"]), (0.0, 0.0, []))

    def test_impossible_counts_rejected(self):
        with self.assertRaises(ValueError):
            ra.weekly_review(messages_sent=5, replies_received=10, dates_booked=0)
        with self.assertRaises(ValueError):
            ra.weekly_review(messages_sent=10, replies_received=5, dates_booked=10)


if __name__ == "__main__":
    unittest.main()
