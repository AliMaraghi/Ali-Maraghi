"""DPIF v1 (APEX Build Order step 5, brutal-honesty directive, 2026-11-15): three critical
controls enforced in code, each with its own test. All synthetic fixtures."""
import tempfile
import time
import unittest
from pathlib import Path

from apex.kernel import budget_signing, persona
from apex.kernel.memory import Ledger

TEST_PRIVATE_KEY, TEST_PUBLIC_KEY = budget_signing.generate_keypair()


class DPIFBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.ledger = Ledger(self.root)

    def tearDown(self):
        self.ledger.close()
        self.tmp.cleanup()


class VoiceOwnershipTests(DPIFBase):
    def test_voice_ownership_rejects_non_owner(self):
        """Critical control 1: no identity other than 'owner' may author a card claiming
        voice_authorized=True."""
        with self.assertRaises(persona.PersonaIsolationError) as ctx:
            persona.write_persona_card(self.ledger, "owner_twin", "Ario", "male", True,
                                       "disclosure text", "some_agent", TEST_PRIVATE_KEY)
        self.assertIn("VOICE_OWNERSHIP_DENIED", str(ctx.exception))
        # The owner identity itself is unaffected.
        persona.write_persona_card(self.ledger, "owner_twin", "Ario", "male", True,
                                   "disclosure text", persona.OWNER_IDENTITY, TEST_PRIVATE_KEY)
        self.assertTrue(persona.read_persona_card(self.ledger, "owner_twin")["voice_authorized"])
        # voice_authorized=False from a non-owner is fine - only the TRUE claim is gated.
        persona.write_persona_card(self.ledger, "companion", "Nova", "female", False,
                                   "disclosure text", "some_agent", TEST_PRIVATE_KEY)


class SyntheticDisclosureTests(DPIFBase):
    def test_synthetic_disclosure_present_each_session(self):
        """Critical control 2: session_disclosure() always returns the CURRENT card's
        disclosure text, re-read fresh every call - simulating "each session" by calling it
        multiple times, including after a disclosure-text correction (new card version)."""
        persona.write_persona_card(self.ledger, "companion", "Nova", "female", False,
                                   "I am a synthetic companion, not a real person.", "owner",
                                   TEST_PRIVATE_KEY, now=1.0)
        for _ in range(3):      # "each session" - called repeatedly, never cached
            self.assertEqual(persona.session_disclosure(self.ledger, "companion"),
                             "I am a synthetic companion, not a real person.")
        persona.write_persona_card(self.ledger, "companion", "Nova", "female", False,
                                   "I am a synthetic companion persona. I have no human feelings.", "owner",
                                   TEST_PRIVATE_KEY, now=2.0)
        self.assertEqual(persona.session_disclosure(self.ledger, "companion"),
                         "I am a synthetic companion persona. I have no human feelings.")

    def test_session_disclosure_refuses_an_unconfigured_persona(self):
        with self.assertRaises(persona.PersonaIsolationError):
            persona.session_disclosure(self.ledger, "nobody")


class KillSwitchTests(DPIFBase):
    def test_kill_switch_under_1s(self):
        """Critical control 3: activation and its enforcement are both measured, real
        wall-clock operations - no avatar/voice runtime exists yet to shut down (subsystems
        A-D are not built), so this measures the record-keeping half: write the kill fact,
        then confirm the VERY NEXT read is blocked, end to end, in well under 1 second."""
        persona.write_persona_card(self.ledger, "companion", "Nova", "female", False,
                                   "disclosure", "owner", TEST_PRIVATE_KEY)
        fid = persona.remember(self.ledger, "companion", "a shared memory", persona.SHARED, "voice")
        self.assertFalse(persona.is_killed(self.ledger, "companion"))
        persona.recall_fact(self.ledger, "companion", fid)    # works before the kill switch

        t0 = time.perf_counter()
        persona.activate_kill_switch(self.ledger, "companion", "owner")
        with self.assertRaises(persona.PersonaIsolationError) as ctx:
            persona.recall_fact(self.ledger, "companion", fid)
        elapsed_s = time.perf_counter() - t0

        self.assertIn("KILL_SWITCH_ACTIVE", str(ctx.exception))
        self.assertTrue(persona.is_killed(self.ledger, "companion"))
        self.assertLess(elapsed_s, 1.0)
        print(f"KILL_SWITCH measured activation+enforcement latency = {elapsed_s * 1000:.3f}ms")

    def test_kill_switch_also_blocks_new_memories(self):
        persona.write_persona_card(self.ledger, "companion", "Nova", "female", False,
                                   "disclosure", "owner", TEST_PRIVATE_KEY)
        persona.activate_kill_switch(self.ledger, "companion", "owner")
        with self.assertRaises(persona.PersonaIsolationError) as ctx:
            persona.remember(self.ledger, "companion", "new memory", persona.SHARED, "voice")
        self.assertIn("KILL_SWITCH_ACTIVE", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
