"""The ledger file runs in WAL mode, and read-only opens still work beside a writer."""
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "core"))
from apex.kernel.memory import Ledger  # noqa: E402


class LedgerWalTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        with Ledger(self.root):
            pass
        self.path = self.root / "runtime" / "kernel.sqlite3"

    def test_mode_is_stored_in_the_file(self):
        with sqlite3.connect(self.path) as db:
            self.assertEqual(db.execute("PRAGMA journal_mode").fetchone()[0], "wal")

    def test_read_only_open_with_no_side_files(self):
        self.assertEqual([p.name for p in self.path.parent.iterdir()], ["kernel.sqlite3"])
        with Ledger.read_only(self.root) as ledger:
            ledger.db.execute("SELECT COUNT(*) FROM events").fetchone()

    def test_reader_does_not_wait_for_an_open_write(self):
        writer = Ledger(self.root)
        writer.db.execute("BEGIN IMMEDIATE")
        try:
            with Ledger.read_only(self.root) as ledger:
                ledger.db.execute("SELECT COUNT(*) FROM events").fetchone()
        finally:
            writer.db.execute("ROLLBACK")
            writer.close()

    def test_second_writer_can_open(self):
        first, second = Ledger(self.root), Ledger(self.root)
        second.close()
        first.close()


if __name__ == "__main__":
    unittest.main()
