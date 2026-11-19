import sqlite3, sys, tempfile, unittest
from pathlib import Path
R = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R / "scripts"))
import db_recover


class Recover(unittest.TestCase):
    def test_salvage_reads_around_a_damaged_page_and_swap_restores(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root / "runtime").mkdir(mode=0o700)
            live = root / "runtime" / "kernel.sqlite3"
            db = sqlite3.connect(live)
            db.execute("CREATE TABLE events (seq INTEGER PRIMARY KEY, event_key TEXT UNIQUE, payload TEXT)")
            db.executemany("INSERT INTO events (event_key, payload) VALUES (?, ?)", [(f"k{i}", "x" * 500) for i in range(2000)])
            db.commit(); db.close()
            raw = bytearray(live.read_bytes())
            raw[4096 * 40: 4096 * 41] = b"\xff" * 4096           # wreck one page in the middle
            live.write_bytes(raw)
            with self.assertRaises(sqlite3.DatabaseError):
                c = sqlite3.connect(live); c.execute("SELECT COUNT(payload) FROM events").fetchone()
            report = db_recover.salvage(root)
            self.assertEqual(report["status"], "SALVAGED")
            self.assertGreater(report["tables"]["events"]["saved"], 1900)
            self.assertEqual(db_recover.swap(root)["status"], "SWAPPED")
            c = sqlite3.connect(live)
            self.assertEqual(c.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertGreater(c.execute("SELECT COUNT(payload) FROM events").fetchone()[0], 1900)
            self.assertEqual(len(list((root / "runtime" / "recovery").glob("*.damaged.sqlite3"))), 1)
