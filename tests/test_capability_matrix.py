"""The capability matrix must stay honest: every file exists, every domain is covered, nothing claims a verified live link."""
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOMAINS = {"finance", "email", "messaging", "social", "dating", "infrastructure", "health", "location", "media"}
FIELDS = {"domain", "service", "requested_operation", "interface", "documentation", "permissions_or_eligibility",
          "implemented_files", "checks_executed", "live_status", "blocker", "smallest_next_action", "implementation"}
IMPLEMENTATION = {"NOT_IMPLEMENTED", "PARTIAL_OFFLINE", "IMPLEMENTED_OFFLINE", "PARTIAL_LIVE"}


class CapabilityMatrixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads((ROOT / "docs/apex_status/CAPABILITY_MATRIX.json").read_text())["services"]

    def test_all_requested_domains_are_present(self):
        self.assertEqual({r["domain"] for r in self.data}, DOMAINS)

    def test_every_entry_is_complete(self):
        for r in self.data:
            self.assertEqual(set(r), FIELDS, r["service"])
            self.assertTrue(r["blocker"] and r["smallest_next_action"] and r["live_status"], r["service"])
            self.assertIn(r["implementation"], IMPLEMENTATION, r["service"])

    def test_listed_files_exist(self):
        for r in self.data:
            for f in r["implemented_files"]:
                self.assertTrue((ROOT / f).exists(), f"{r['service']}: {f}")

    def test_no_entry_claims_a_verified_live_connection(self):
        for r in self.data:
            self.assertNotIn("LIVE_VERIFIED", r["live_status"], r["service"])
            self.assertNotEqual(r["live_status"], "CONNECTED", r["service"])

    def test_unimplemented_entries_list_no_implementation_files(self):
        for r in self.data:
            if r["implementation"] == "NOT_IMPLEMENTED" and r["domain"] not in {"messaging", "social"}:
                self.assertEqual(r["implemented_files"], [], r["service"])


if __name__ == "__main__":
    unittest.main()
