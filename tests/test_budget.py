"""Offline tests: cost registry, zero-by-default budget, atomic reservation, retries, concurrency."""
import tempfile
import threading
import unittest
from pathlib import Path

from apex.kernel.budget import Budget, BudgetDenied, STALE_AFTER, window_start
from apex.kernel.memory import Ledger

T0 = 1_800_000_000.0          # 2027-01-15 08:00:00 UTC (a Friday)


class BudgetTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.ledger = Ledger(self.root)
        self.now = [T0]
        self.b = Budget(self.ledger, clock=lambda: self.now[0])
        self.b.set_price("mock", "echo", 0, 0, "synthetic mock provider")
        self.b.set_price("acme", "video-sec", 12_000, T0 - 10, "https://example.test/pricing")   # 12p per unit

    def tearDown(self):
        self.ledger.close()
        self.tmp.cleanup()

    def test_default_blocks_paid_but_allows_registered_mock(self):
        self.assertEqual(self.b.reserve("m1", "core", "mock", "echo", 1000), "RESERVED")
        with self.assertRaisesRegex(BudgetDenied, "NO_CAP_CONFIGURED"):
            self.b.reserve("p1", "studio", "acme", "video-sec", 1)

    def test_unknown_and_stale_and_future_prices_block(self):
        self.b.set_cap("studio", "month", 1000)
        with self.assertRaisesRegex(BudgetDenied, "UNKNOWN_PRICE"):
            self.b.reserve("u1", "studio", "acme", "other-sku", 1)
        self.b.set_price("acme", "future", 100, T0 + 3600, "https://example.test/new")
        with self.assertRaisesRegex(BudgetDenied, "UNKNOWN_PRICE"):
            self.b.reserve("f1", "studio", "acme", "future", 1)
        self.now[0] += STALE_AFTER + 10
        with self.assertRaisesRegex(BudgetDenied, "STALE_PRICE"):
            self.b.reserve("s1", "studio", "acme", "video-sec", 1)

    def test_effective_dated_price_uses_the_price_in_force(self):
        self.b.set_cap("studio", "month", 10_000)
        self.b.set_price("acme", "video-sec", 24_000, T0 + 100, "https://example.test/pricing-v2")
        self.b.reserve("a", "studio", "acme", "video-sec", 1)              # old price: 12p
        self.now[0] += 200
        self.b.set_price("acme", "video-sec", 24_000, T0 + 100, "https://example.test/pricing-v2")
        self.b.reserve("b", "studio", "acme", "video-sec", 1)              # new price: 24p
        rows = dict(self.ledger.db.execute("SELECT key,reserved_minor FROM budget_reservations"))
        self.assertEqual((rows["a"], rows["b"]), (12, 24))

    def test_ceiling_to_pence_and_cap_enforced_by_period(self):
        self.b.set_price("acme", "tiny", 100, 0, "https://example.test/t")       # 0.1p per unit
        self.b.set_cap("core", "day", 5)
        self.b.reserve("c1", "core", "acme", "tiny", 41)                         # 4.1p -> 5p
        with self.assertRaisesRegex(BudgetDenied, "CAP_EXCEEDED:core:day"):
            self.b.reserve("c2", "core", "acme", "tiny", 1)
        self.now[0] += 86400                                                     # next UTC day: window resets
        self.assertEqual(self.b.reserve("c3", "core", "acme", "tiny", 1), "RESERVED")

    def test_global_cap_spans_pools(self):
        for pool in ("core", "studio"):
            self.b.set_cap(pool, "month", 2000)
        self.b.set_cap("global", "month", 2000)                                  # £20
        self.b.reserve("g1", "core", "acme", "video-sec", 100)                   # £12
        with self.assertRaisesRegex(BudgetDenied, "CAP_EXCEEDED:global:month"):
            self.b.reserve("g2", "studio", "acme", "video-sec", 100)

    def test_monthly_hard_cap_cannot_be_raised_by_configuration(self):
        from apex.kernel.budget import HardBudgetExceeded, MONTHLY_HARD_CAP_PENCE
        for pool in ("core", "studio"):
            self.b.set_cap(pool, "month", 1_000_000)                             # owner sets absurd caps
        self.b.set_cap("global", "month", 1_000_000)
        self.b.reserve("h1", "core", "acme", "video-sec", 150)                   # £18.00
        with self.assertRaisesRegex(HardBudgetExceeded, "MONTHLY_HARD_CAP"):
            self.b.reserve("h2", "studio", "acme", "video-sec", 20)              # +£2.40 would pass £20
        self.b.reserve("h3", "studio", "acme", "video-sec", 16)                  # +£1.92 still fits
        status = self.b.month_status()
        self.assertEqual(status["spent_pence"], 1992)
        self.assertLessEqual(status["spent_pence"], MONTHLY_HARD_CAP_PENCE)
        self.assertTrue(status["warning"])
        self.b.reserve("free", "core", "mock", "echo", 5)                        # zero-cost work is never blocked
        self.now[0] += 32 * 86400                                                # next calendar month
        self.b.set_price("acme", "video-sec", 12_000, self.now[0] - 10, "https://example.test/pricing")
        self.b.reserve("h4", "core", "acme", "video-sec", 20)                    # resumes on its own

    def test_retries_use_their_own_pool_and_must_name_original(self):
        self.b.set_cap("core", "day", 1000)
        self.b.reserve("r0", "core", "acme", "video-sec", 1)
        with self.assertRaises(ValueError):
            self.b.reserve("r1", "retry", "acme", "video-sec", 1)               # missing retry_of
        with self.assertRaisesRegex(BudgetDenied, "NO_CAP_CONFIGURED"):
            self.b.reserve("r1", "retry", "acme", "video-sec", 1, retry_of="r0")  # core cap cannot pay retries
        self.b.set_cap("retry", "day", 100)
        self.assertEqual(self.b.reserve("r1", "retry", "acme", "video-sec", 1, retry_of="r0"), "RESERVED")

    def test_idempotent_and_conflicting_keys(self):
        self.b.set_cap("core", "day", 1000)
        self.b.reserve("i1", "core", "acme", "video-sec", 2)
        self.assertEqual(self.b.reserve("i1", "core", "acme", "video-sec", 2), "RESERVED")
        self.assertEqual(self.ledger.db.execute("SELECT SUM(reserved_minor) FROM budget_reservations").fetchone()[0], 24)
        with self.assertRaises(ValueError):
            self.b.reserve("i1", "core", "acme", "video-sec", 3)

    def test_settle_release_and_overrun_are_accounted(self):
        self.b.set_cap("core", "day", 100)
        self.b.reserve("s1", "core", "acme", "video-sec", 5)                     # 60p reserved
        self.assertEqual(self.b.settle("s1", 3), 36)                              # actual 36p frees 24p
        self.b.reserve("s2", "core", "acme", "video-sec", 5)                      # 60p -> 96p
        self.b.release("s2")                                                      # released -> 36p
        self.b.reserve("s3", "core", "acme", "video-sec", 5)                      # 96p
        self.assertEqual(self.b.settle("s3", 8), 96)                              # overrun counted
        events = [r["payload"] for r in self.ledger.records("personal") if r["key"] == "bud.s3.s"]
        self.assertTrue(events[0]["overrun"])
        with self.assertRaises(BudgetDenied):
            self.b.settle("s3", 1)                                                # cannot settle twice

    def test_concurrent_reservations_never_exceed_cap(self):
        self.b.set_cap("core", "day", 50)
        wins, errors = [], []

        def worker(i):
            with Ledger(self.root) as ledger:
                budget = Budget(ledger, clock=lambda: T0)
                try:
                    budget.reserve(f"w{i}", "core", "acme", "video-sec", 1)   # 12p each -> at most 4 fit in 50p
                    wins.append(i)
                except BudgetDenied:
                    pass
                except Exception as exc:                                       # pragma: no cover
                    errors.append(exc)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(12)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        self.assertEqual(errors, [])
        self.assertEqual(len(wins), 4)
        self.assertLessEqual(self.b.spent("core", "day", T0), 50)

    def test_window_boundaries(self):
        self.assertEqual(window_start("day", T0), T0 - 8 * 3600)
        self.assertEqual(window_start("week", T0), T0 - 8 * 3600 - 4 * 86400)    # Monday 00:00Z
        self.assertEqual(window_start("month", T0), T0 - 8 * 3600 - 14 * 86400)


if __name__ == "__main__":
    unittest.main()
