"""Phase 7 gate: scripts/choose_domain.py prints exactly the specified text, no hedging."""
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

EXPECTED = (
    "ACTIVE DOMAIN SELECTION:\n"
    "[1] Email Management (Requires IMAP/SMTP access)\n"
    "[2] Bill Processing (Requires PDF parsing + Bank API)\n"
    "[3] Calendar Optimization (Requires Google Calendar OAuth)\n"
    "Select the ONE domain to activate for the next 21 days: "
)


class ChooseDomainTests(unittest.TestCase):
    def test_exact_output(self):
        result = subprocess.run([sys.executable, "-B", str(ROOT / "scripts" / "choose_domain.py")],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, EXPECTED)


if __name__ == "__main__":
    unittest.main()
