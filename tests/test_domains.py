"""Multi-domain scaffolding, single-domain activation (mission 2026-11-15). Synthetic
fixtures only - no real bank/email/calendar access anywhere in these tests."""
import json
import tempfile
import unittest
from pathlib import Path

from apex.action_domains import bills, calendar, email, router


class BillsDomainTests(unittest.TestCase):
    def test_synthetic_bill_produces_a_proposal(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bills.json"
            path.write_text(json.dumps({"vendor": "AWS", "amount_pence": 4500, "due_date": "2026-11-20"}))
            proposal = bills.make_proposal(path)
        self.assertIsNotNone(proposal)
        self.assertEqual(proposal.vendor, "AWS")
        self.assertTrue(proposal.requires_owner_review)
        self.assertTrue(proposal.risks)

    def test_missing_file_produces_no_proposal(self):
        self.assertIsNone(bills.make_proposal(Path("/nonexistent/bills.json")))

    def test_high_amount_flagged_as_urgent_risk(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bills.json"
            path.write_text(json.dumps({"vendor": "Landlord", "amount_pence": 150_000, "due_date": "2026-11-16"}))
            proposal = bills.make_proposal(path)
        self.assertTrue(any("exceeds" in r for r in proposal.risks))


class EmailDomainTests(unittest.TestCase):
    def test_synthetic_email_produces_a_draft(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "email_inbox.json"
            path.write_text(json.dumps({"sender": "boss@company.com", "subject": "Urgent meeting"}))
            proposal = email.make_proposal(path)
        self.assertIsNotNone(proposal)
        self.assertEqual(proposal.sender, "boss@company.com")
        self.assertTrue(proposal.requires_owner_review)

    def test_missing_file_produces_no_proposal(self):
        self.assertIsNone(email.make_proposal(Path("/nonexistent/email_inbox.json")))


class CalendarDomainTests(unittest.TestCase):
    def test_synthetic_conflict_produces_a_proposal(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "calendar_conflict.json"
            path.write_text(json.dumps({"event_a": "Standup", "event_b": "Dentist",
                                        "conflict_window": "2026-11-17 09:00-09:30"}))
            proposal = calendar.make_proposal(path)
        self.assertIsNotNone(proposal)
        self.assertIn("Standup", proposal.conflict_description)
        self.assertTrue(proposal.requires_owner_review)

    def test_missing_file_produces_no_proposal(self):
        self.assertIsNone(calendar.make_proposal(Path("/nonexistent/calendar_conflict.json")))


class RouterTests(unittest.TestCase):
    def test_active_domain_is_bills(self):
        self.assertEqual(router.ACTIVE_DOMAIN, router.Domain.BILLS)

    def test_router_only_runs_active_domain(self):
        """The critical gate: given all three domains, only BILLS is active; EMAIL and
        CALENDAR must report is_active() == False with the exact specified skip message."""
        for domain in router.Domain:
            active = router.is_active(domain)
            if domain == router.Domain.BILLS:
                self.assertTrue(active)
            else:
                self.assertFalse(active)
                self.assertEqual(router.skip_message(domain),
                                 f"[SKIPPED] Domain {domain.value} is STAGED. Active domain is bills")


if __name__ == "__main__":
    unittest.main()
