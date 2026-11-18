"""Off-site backup: preconditions, once-a-day pacing, real encryption round trip, pruning."""
import gzip
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "core"))
from apex import drive_backup as backup  # noqa: E402
from apex.kernel.memory import Ledger  # noqa: E402

SCOPE = "openid email https://www.googleapis.com/auth/gmail.readonly " + backup.DRIVE_SCOPE
PASSPHRASE = "correct horse battery staple 2026"


class DriveBackupTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.key = self.root / "passphrase"
        self.key.write_text(PASSPHRASE)
        os.chmod(self.key, 0o600)
        self.sent = []
        self.removed = []

    def run_once(self, ledger, now, scope=SCOPE, key=None, fail=False):
        def uploader(token, name, blob):
            if fail:
                raise backup.BackupError("DRIVE_UPLOAD_REJECTED")
            self.sent.append((token, name, blob))
            return "file-id-%04d-abcdef" % len(self.sent)
        return backup.run_if_due(ledger, self.root, scope, lambda: "token", now, str(key or self.key),
                                 uploader, lambda token, file_id: self.removed.append(file_id) or True)

    def test_idle_without_drive_scope_or_passphrase(self):
        with Ledger(self.root) as ledger:
            self.assertIsNone(self.run_once(ledger, 1000, scope="openid email"))
            self.assertIsNone(self.run_once(ledger, 1000, key=self.root / "missing"))
            self.assertIn("Drive permission", backup.status(ledger, "openid", str(self.key)))
            self.assertIn("passphrase", backup.status(ledger, SCOPE, str(self.root / "missing")))
        self.assertEqual(self.sent, [])

    def test_passphrase_file_must_be_private(self):
        os.chmod(self.key, 0o644)
        self.assertFalse(backup.passphrase_ready(str(self.key)))
        os.chmod(self.key, 0o600)
        self.key.write_text("short")
        self.assertFalse(backup.passphrase_ready(str(self.key)))

    def test_upload_decrypts_to_the_journal_and_runs_once_a_day(self):
        with Ledger(self.root) as ledger:
            self.assertEqual(self.run_once(ledger, 100000), "UPLOADED")
            self.assertIsNone(self.run_once(ledger, 100000 + 3600))
            self.assertEqual(self.run_once(ledger, 100000 + backup.INTERVAL), "UPLOADED")
            self.assertIn("last upload", backup.status(ledger, SCOPE, str(self.key)))
        _, name, blob = self.sent[0]
        self.assertTrue(name.startswith("apex-journal-") and name.endswith(".sqlite3.gz.enc"))
        self.assertNotIn(b"SQLite format 3", blob)
        plain = subprocess.run(["openssl", "enc", "-d", "-aes-256-cbc", "-pbkdf2", "-iter", backup.ITERATIONS,
                                "-pass", "file:" + str(self.key)], input=blob, capture_output=True, check=True).stdout
        restored = self.root / "restored.sqlite3"
        restored.write_bytes(gzip.decompress(plain))
        with sqlite3.connect(restored) as db:
            self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertTrue(db.execute("SELECT 1 FROM sqlite_master WHERE name='events'").fetchone())
        self.assertEqual(list((self.root / "runtime").glob("apex-backup-*")), [])

    def test_failure_is_recorded_and_retried_only_after_an_hour(self):
        with Ledger(self.root) as ledger:
            self.assertEqual(self.run_once(ledger, 5000, fail=True), "DRIVE_UPLOAD_REJECTED")
            self.assertIsNone(self.run_once(ledger, 5000 + 60))
            self.assertEqual(self.run_once(ledger, 5000 + backup.RETRY_AFTER), "UPLOADED")
            ledger.verify()

    def test_old_uploads_are_pruned(self):
        with Ledger(self.root) as ledger:
            for day in range(backup.KEEP + 2):
                self.assertEqual(self.run_once(ledger, 100000 + day * backup.INTERVAL), "UPLOADED")
        self.assertEqual(self.removed[0], "file-id-0001-abcdef")
        self.assertGreaterEqual(len(self.removed), 2)


if __name__ == "__main__":
    unittest.main()
