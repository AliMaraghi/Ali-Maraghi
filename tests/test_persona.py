"""Persona-card memory (Digital Twin extension, subsystem 2.E, 2026-11-15). All synthetic
fixtures. Proves: append-only persona cards with a mandatory disclosure field (DPIF critical
control 2), the shared-vs-private memory boundary as a REAL deny-by-default check, export,
and that no deletion function pretends to delete anything it cannot."""
import tempfile
import unittest
from pathlib import Path

from apex.kernel import persona
from apex.kernel.memory import Ledger


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
            persona.write_persona_card(self.ledger, "owner_twin", "Ario", "male", True, "", "owner")
        with self.assertRaises(ValueError):
            persona.write_persona_card(self.ledger, "owner_twin", "Ario", "male", True, "   ", "owner")

    def test_voice_authorized_must_be_an_explicit_boolean(self):
        with self.assertRaises(ValueError):
            persona.write_persona_card(self.ledger, "owner_twin", "Ario", "male", "yes",
                                       "I am a synthetic representation of the owner.", "owner")

    def test_card_round_trips_and_history_is_append_only(self):
        persona.write_persona_card(self.ledger, "companion", "Nova", "female",
                                   False, "I am a synthetic companion persona, not a real person.", "owner", now=1.0)
        card = persona.read_persona_card(self.ledger, "companion")
        self.assertEqual(card["display_name"], "Nova")
        self.assertFalse(card["voice_authorized"])
        persona.write_persona_card(self.ledger, "companion", "Nova v2", "female",
                                   False, "I am a synthetic companion persona, not a real person.", "owner", now=2.0)
        history = persona.persona_card_history(self.ledger, "companion")
        self.assertEqual(len(history), 2)                          # old version preserved, not overwritten
        self.assertEqual(persona.read_persona_card(self.ledger, "companion")["display_name"], "Nova v2")

    def test_unconfigured_persona_has_no_card(self):
        self.assertIsNone(persona.read_persona_card(self.ledger, "nobody"))


class MemoryIsolationTests(PersonaBase):
    def setUp(self):
        super().setUp()
        persona.write_persona_card(self.ledger, "owner_twin", "Ario", "male", True,
                                   "I am an authorised synthetic representation of the owner.", "owner", now=1.0)
        persona.write_persona_card(self.ledger, "companion", "Nova", "female", False,
                                   "I am a synthetic companion persona, not a real person.", "owner", now=1.0)

    def test_cannot_remember_for_a_persona_with_no_card(self):
        with self.assertRaises(persona.PersonaIsolationError):
            persona.remember(self.ledger, "ghost", "some memory", persona.SHARED, "voice")

    def test_invalid_visibility_is_rejected(self):
        with self.assertRaises(ValueError):
            persona.remember(self.ledger, "owner_twin", "x", "public", "voice")

    def test_a_persona_always_reads_its_own_shared_and_private_memories(self):
        persona.remember(self.ledger, "owner_twin", "owner likes climbing", persona.SHARED, "voice", now=2.0)
        persona.remember(self.ledger, "owner_twin", "owner's private worry about work", persona.PRIVATE, "voice", now=3.0)
        own = persona.recall(self.ledger, "owner_twin", "owner_twin")
        texts = [m["object"] for m in own]
        self.assertIn("owner likes climbing", texts)
        self.assertIn("owner's private worry about work", texts)

    def test_another_persona_can_read_only_what_was_shared(self):
        persona.remember(self.ledger, "owner_twin", "owner likes climbing", persona.SHARED, "voice", now=2.0)
        persona.remember(self.ledger, "owner_twin", "owner's private worry about work", persona.PRIVATE, "voice", now=3.0)
        companion_view = persona.recall(self.ledger, "companion", "owner_twin")
        texts = [m["object"] for m in companion_view]
        self.assertIn("owner likes climbing", texts)
        self.assertNotIn("owner's private worry about work", texts)     # the enforced boundary

    def test_recall_from_an_unregistered_reading_persona_is_refused_not_silently_empty(self):
        with self.assertRaises(persona.PersonaIsolationError):
            persona.recall(self.ledger, "unregistered_persona", "owner_twin")

    def test_recall_of_an_unregistered_owning_persona_is_refused_not_silently_empty(self):
        with self.assertRaises(persona.PersonaIsolationError):
            persona.recall(self.ledger, "owner_twin", "unregistered_persona")


class ExportTests(PersonaBase):
    def test_export_includes_card_history_and_both_visibilities_for_the_owning_persona(self):
        persona.write_persona_card(self.ledger, "owner_twin", "Ario", "male", True,
                                   "I am an authorised synthetic representation of the owner.", "owner", now=1.0)
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
