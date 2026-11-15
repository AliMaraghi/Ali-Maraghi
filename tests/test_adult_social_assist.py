"""Adult social/dating assistance extension (2026-11-15). All synthetic fixtures - no real
owner identity, no real counterpart profiles, no real platform accounts."""
import tempfile
import unittest
from pathlib import Path

from apex import adult_social_assist as asa
from apex.kernel.memory import Ledger


class PlatformProfileTests(unittest.TestCase):
    def test_all_four_platforms_have_distinct_rationale_and_fields(self):
        seen_rationale = set()
        for platform in asa.PLATFORMS:
            tpl = asa.platform_profile_template(platform)
            self.assertEqual(tpl.platform, platform)
            self.assertTrue(tpl.rationale)
            self.assertNotIn(tpl.rationale, seen_rationale)
            seen_rationale.add(tpl.rationale)
            self.assertIn("ddf_status", tpl.fields + ("ddf_status",))  # DDF present or N/A-explicit

    def test_unknown_platform_rejected(self):
        with self.assertRaises(ValueError):
            asa.platform_profile_template("okcupid")


class FirstMessageDraftTests(unittest.TestCase):
    def test_valid_draft_produced(self):
        d = asa.draft_first_message(
            "their profile says: couple, North London, MFM, respectful single male welcome",
            "Hi both, I'm into the same scene and based nearby.",
            "Happy to chat here first - what are you hoping to find?")
        self.assertFalse(d.send)
        self.assertTrue(d.requires_owner_review)

    def test_explicit_image_in_first_message_refused(self):
        with self.assertRaises(asa.EtiquetteRefused):
            asa.draft_first_message("their profile says X", "intro", "question?", includes_explicit_image=True)

    def test_too_many_sentences_rejected(self):
        with self.assertRaises(ValueError):
            asa.draft_first_message(
                "their profile says X",
                "One. Two. Three.",
                "Four? Five?")

    def test_guard_still_refuses_automation_language(self):
        with self.assertRaises(asa.AssistRefused):
            asa.draft_first_message("their profile says X", "auto-reply to everyone for me", "ok?")


class EtiquetteGuardTests(unittest.TestCase):
    """S4 gate: all 6 named patterns must be rejected."""

    def test_1_duplicate_copy_paste_rejected(self):
        with self.assertRaises(asa.EtiquetteRefused):
            asa.etiquette_guard("Hi there, loved your profile!", is_duplicate_of_others=True)

    def test_2_content_free_opener_rejected(self):
        for opener in ("Hi", "Hey", "U up?", "hello."):
            with self.assertRaises(asa.EtiquetteRefused):
                asa.etiquette_guard(opener)

    def test_3_explicit_image_rejected(self):
        with self.assertRaises(asa.EtiquetteRefused):
            asa.etiquette_guard("a real specific message", includes_explicit_image=True)

    def test_4_immediate_meetup_pressure_rejected(self):
        with self.assertRaises(asa.EtiquetteRefused):
            asa.etiquette_guard("Can you meet tonight?")

    def test_5_insistence_after_no_rejected(self):
        with self.assertRaises(asa.EtiquetteRefused):
            asa.etiquette_guard("a real specific message", after_a_no=True)

    def test_6_profile_mismatch_rejected(self):
        with self.assertRaises(asa.EtiquetteRefused):
            asa.etiquette_guard("a real specific message", profile_mismatch=True)

    def test_a_real_specific_message_passes(self):
        asa.etiquette_guard("Saw you mentioned the Stoke Newington FetLife meetup - do you go often?")


class ResponseClassificationTests(unittest.TestCase):
    def test_interested(self):
        self.assertEqual(asa.classify_response("Yeah sounds great, would love to chat more!"), "interested")

    def test_cold(self):
        self.assertEqual(asa.classify_response("No thanks, not interested"), "cold")

    def test_neutral_default(self):
        self.assertEqual(asa.classify_response("maybe, tell me more about yourself"), "neutral")

    def test_empty_is_neutral(self):
        self.assertEqual(asa.classify_response(""), "neutral")

    def test_next_step_mapping(self):
        self.assertEqual(asa.next_step_for("cold"), "close_respectfully")
        self.assertEqual(asa.next_step_for("interested"), "propose_public_meetup")
        self.assertEqual(asa.next_step_for("neutral"), "ask_a_discovery_question")
        with self.assertRaises(ValueError):
            asa.next_step_for("ecstatic")


class SafetyChecklistTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger = Ledger(Path(self.tmp.name))

    def tearDown(self):
        self.ledger.close()
        self.tmp.cleanup()

    def test_complete_checklist_recorded(self):
        confirmed = {item: True for item in asa.SAFETY_CHECKLIST_ITEMS}
        confirmed["own_recent_sti_test_status_known"] = False   # honest negative is still recordable
        fid = asa.record_safety_checklist(self.ledger, "A", confirmed, now=1.0)
        from apex.kernel import facts
        row = facts.get_fact(self.ledger, fid)
        self.assertEqual(row["subject"], "adult_social:A")
        self.assertIn("safeword_agreed_if_bdsm=True", row["object"])

    def test_incomplete_checklist_rejected(self):
        confirmed = {item: True for item in asa.SAFETY_CHECKLIST_ITEMS}
        del confirmed["no_means_no_no_argument"]
        with self.assertRaises(ValueError):
            asa.record_safety_checklist(self.ledger, "A", confirmed, now=1.0)


if __name__ == "__main__":
    unittest.main()
