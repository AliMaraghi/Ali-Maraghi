"""Persona-card memory (Digital Twin extension, subsystem 2.E, 2026-11-15). All synthetic
fixtures. Proves: append-only, SIGNED persona cards with a mandatory disclosure field (DPIF
critical control 2), the shared-vs-private memory boundary plus the data_class/grants
boundary as REAL deny-by-default checks (including signature-verified grants - the HOLE
closed 2026-11-15), export, and that no deletion function pretends to delete anything it
cannot."""
import tempfile
import unittest
from pathlib import Path

from apex.kernel import budget_signing, persona
from apex.kernel.memory import Ledger

TEST_PRIVATE_KEY, TEST_PUBLIC_KEY = budget_signing.generate_keypair()      # synthetic test key


class PersonaBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.ledger = Ledger(self.root)

    def tearDown(self):
        self.ledger.close()
        self.tmp.cleanup()


class PersonaCardTests(PersonaBase):
    def test_disclosure_text_is_mandatory(self):
        with self.assertRaises(ValueError):
            persona.write_persona_card(self.ledger, "owner_twin", "Ario", "male", True, "", "owner", TEST_PRIVATE_KEY)
        with self.assertRaises(ValueError):
            persona.write_persona_card(self.ledger, "owner_twin", "Ario", "male", True, "   ", "owner", TEST_PRIVATE_KEY)

    def test_voice_authorized_must_be_an_explicit_boolean(self):
        with self.assertRaises(ValueError):
            persona.write_persona_card(self.ledger, "owner_twin", "Ario", "male", "yes",
                                       "I am a synthetic representation of the owner.", "owner", TEST_PRIVATE_KEY)

    def test_private_key_bytes_is_mandatory(self):
        with self.assertRaises(ValueError):
            persona.write_persona_card(self.ledger, "owner_twin", "Ario", "male", True,
                                       "disclosure", "owner", b"too short")

    def test_card_round_trips_and_history_is_append_only(self):
        persona.write_persona_card(self.ledger, "companion", "Nova", "female", False,
                                   "I am a synthetic companion persona, not a real person.", "owner",
                                   TEST_PRIVATE_KEY, now=1.0)
        card = persona.read_persona_card(self.ledger, "companion")
        self.assertEqual(card["display_name"], "Nova")
        self.assertFalse(card["voice_authorized"])
        self.assertEqual(card["version"], 1)
        self.assertIsNone(card["prev_card_sig"])
        persona.write_persona_card(self.ledger, "companion", "Nova v2", "female", False,
                                   "I am a synthetic companion persona, not a real person.", "owner",
                                   TEST_PRIVATE_KEY, now=2.0)
        history = persona.persona_card_history(self.ledger, "companion")
        self.assertEqual(len(history), 2)                          # old version preserved, not overwritten
        current = persona.read_persona_card(self.ledger, "companion")
        self.assertEqual(current["display_name"], "Nova v2")
        self.assertEqual(current["version"], 2)
        self.assertEqual(current["prev_card_sig"], history[1]["card"]["owner_sig"])    # chains to v1's own sig

    def test_unconfigured_persona_has_no_card(self):
        self.assertIsNone(persona.read_persona_card(self.ledger, "nobody"))


class CardSignatureTests(PersonaBase):
    """The HOLE, closed: grants (and every other card field) are now signed, so DB-level
    tampering is detectable - the gate is no longer enforced by unsigned data."""
    def test_a_freshly_written_card_verifies(self):
        persona.write_persona_card(self.ledger, "companion", "Nova", "female", False,
                                   "disclosure", "owner", TEST_PRIVATE_KEY, grants=[], now=1.0)
        self.assertTrue(persona.verify_persona_card(self.ledger, "companion", TEST_PUBLIC_KEY))

    def test_tampering_grants_directly_in_the_db_fails_verification(self):
        import json
        fact_id = persona.write_persona_card(self.ledger, "companion", "Nova", "female", False,
                                             "disclosure", "owner", TEST_PRIVATE_KEY, grants=[], now=1.0)
        card = persona.read_persona_card(self.ledger, "companion")
        card["grants"] = ["MEDICAL"]      # the attack: add a grant without re-signing
        self.ledger.db.execute("UPDATE facts SET object=? WHERE id=?", (json.dumps(card), fact_id))
        self.assertFalse(persona.verify_persona_card(self.ledger, "companion", TEST_PUBLIC_KEY))

    def test_wrong_public_key_fails_verification(self):
        persona.write_persona_card(self.ledger, "companion", "Nova", "female", False,
                                   "disclosure", "owner", TEST_PRIVATE_KEY, now=1.0)
        _, wrong_public_key = budget_signing.generate_keypair()
        self.assertFalse(persona.verify_persona_card(self.ledger, "companion", wrong_public_key))

    def test_an_unconfigured_persona_fails_verification_not_raises(self):
        self.assertFalse(persona.verify_persona_card(self.ledger, "nobody", TEST_PUBLIC_KEY))


class MemoryIsolationTests(PersonaBase):
    def setUp(self):
        super().setUp()
        persona.write_persona_card(self.ledger, "owner_twin", "Ario", "male", True,
                                   "I am an authorised synthetic representation of the owner.", "owner",
                                   TEST_PRIVATE_KEY, now=1.0)
        persona.write_persona_card(self.ledger, "companion", "Nova", "female", False,
                                   "I am a synthetic companion persona, not a real person.", "owner",
                                   TEST_PRIVATE_KEY, now=1.0)

    def test_cannot_remember_for_a_persona_with_no_card(self):
        with self.assertRaises(persona.PersonaIsolationError):
            persona.remember(self.ledger, "ghost", "some memory", persona.SHARED, "voice")

    def test_invalid_visibility_is_rejected(self):
        with self.assertRaises(ValueError):
            persona.remember(self.ledger, "owner_twin", "x", "public", "voice")

    def test_a_persona_always_reads_its_own_shared_and_private_memories(self):
        shared_id = persona.remember(self.ledger, "owner_twin", "owner likes climbing", persona.SHARED, "voice", now=2.0)
        private_id = persona.remember(self.ledger, "owner_twin", "owner's private worry about work",
                                      persona.PRIVATE, "voice", now=3.0)
        self.assertEqual(persona.recall_fact(self.ledger, "owner_twin", shared_id)["object"], "owner likes climbing")
        self.assertEqual(persona.recall_fact(self.ledger, "owner_twin", private_id)["object"],
                         "owner's private worry about work")

    def test_another_persona_can_read_only_what_was_shared_and_public(self):
        shared_id = persona.remember(self.ledger, "owner_twin", "owner likes climbing", persona.SHARED, "voice", now=2.0)
        private_id = persona.remember(self.ledger, "owner_twin", "owner's private worry about work",
                                      persona.PRIVATE, "voice", now=3.0)
        self.assertEqual(persona.recall_fact(self.ledger, "companion", shared_id)["object"], "owner likes climbing")
        with self.assertRaises(persona.PersonaIsolationError):
            persona.recall_fact(self.ledger, "companion", private_id)     # the enforced boundary

    def test_shared_financial_fact_requires_a_verified_grant(self):
        fid = persona.remember(self.ledger, "owner_twin", "F_fin content", persona.SHARED, "voice",
                               data_class="FINANCE", now=2.0)
        with self.assertRaises(persona.PersonaIsolationError) as ctx:
            persona.recall_fact(self.ledger, "companion", fid)          # no public_key_bytes at all -> fail closed
        self.assertIn("PERSONA_CARD_UNVERIFIED", str(ctx.exception))
        with self.assertRaises(persona.PersonaIsolationError) as ctx:
            persona.recall_fact(self.ledger, "companion", fid, TEST_PUBLIC_KEY)   # verified card, but no grant
        self.assertIn("DATA_CLASS_DENIED", str(ctx.exception))

    def test_recall_fact_from_an_unregistered_reading_persona_is_refused(self):
        shared_id = persona.remember(self.ledger, "owner_twin", "owner likes climbing", persona.SHARED, "voice", now=2.0)
        with self.assertRaises(persona.PersonaIsolationError):
            persona.recall_fact(self.ledger, "unregistered_persona", shared_id)

    def test_recall_is_removed_and_raises_not_implemented(self):
        """GAP 2 (brutal-honesty directive, 2026-11-15): the old whole-history recall()
        silently filtered access-denied into an empty list - removed outright."""
        with self.assertRaises(NotImplementedError):
            persona.recall(self.ledger, "owner_twin", "owner_twin")


class ExportTests(PersonaBase):
    def test_export_includes_card_history_and_both_visibilities_for_the_owning_persona(self):
        persona.write_persona_card(self.ledger, "owner_twin", "Ario", "male", True,
                                   "I am an authorised synthetic representation of the owner.", "owner",
                                   TEST_PRIVATE_KEY, now=1.0)
        persona.remember(self.ledger, "owner_twin", "shared memory", persona.SHARED, "voice", now=2.0)
        persona.remember(self.ledger, "owner_twin", "private memory", persona.PRIVATE, "voice", now=3.0)
        export = persona.export_persona_memories(self.ledger, "owner_twin")
        self.assertEqual(export["card"]["display_name"], "Ario")
        self.assertEqual(len(export["card_history"]), 1)
        self.assertEqual([m["object"] for m in export["shared_memories"]], ["shared memory"])
        self.assertEqual([m["object"] for m in export["private_memories"]], ["private memory"])

    def test_export_of_an_unconfigured_persona_is_refused(self):
        with self.assertRaises(persona.PersonaIsolationError):
            persona.export_persona_memories(self.ledger, "nobody")

    def test_no_delete_function_exists_that_could_pretend_to_erase_anything(self):
        """The disclosed limitation made falsifiable: this module exposes no delete/forget/
        erase function at all - better to expose nothing than to expose something that looks
        like deletion but, in an append-only store, is not."""
        exported_names = {n for n in dir(persona) if not n.startswith("_")}
        for forbidden in ("delete", "erase", "forget", "purge", "remove_memory", "wipe"):
            self.assertFalse(any(forbidden in name.lower() for name in exported_names),
                             f"found a function suggesting deletion: {forbidden}")


if __name__ == "__main__":
    unittest.main()
