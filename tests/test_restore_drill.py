import sqlite3, sys, tempfile, unittest
from pathlib import Path
R = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R / "scripts")); sys.path.insert(0, str(R / "core"))
import restore_drill


class Drill(unittest.TestCase):
    def test_round_trip_reconciles_and_leaves_live_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root / "runtime").mkdir()
            live = root / "runtime" / "kernel.sqlite3"
            db = sqlite3.connect(live); db.execute("CREATE TABLE events (seq INTEGER PRIMARY KEY, p TEXT)")
            db.executemany("INSERT INTO events (p) VALUES (?)", [("x" * 50,)] * 300); db.commit(); db.close()
            secret = root / "pass"; secret.write_text("correct horse battery staple 123\n"); secret.chmod(0o600)
            before = live.read_bytes()
            out = restore_drill.drill(root, str(secret))
            if out["status"] == "BLOCKED":
                self.skipTest(out["reason"])
            self.assertEqual(out["status"], "PASS", out)
            self.assertEqual(out["events_restored"], 300)
            self.assertEqual(out["table_differences"], {})
            self.assertEqual(live.read_bytes(), before)

    def test_missing_passphrase_is_reported_not_faked(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(restore_drill.drill(Path(tmp), str(Path(tmp) / "none"))["status"], "BLOCKED")
