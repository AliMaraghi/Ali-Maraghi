"""Monzo adapter contract tests with synthetic fixtures. No network; endpoints per docs.monzo.com (2026-11-12)."""
import json
import unittest
from datetime import datetime, timedelta, timezone

from apex import monzo

TOKEN = "t" * 40
ACC = "acc_0000SyntheticAccount1"


def tx(i, amount=-250, settled="2026-11-01T10:00:00Z", **extra):
    return {"id": f"tx_{i:012d}ABCDEF", "amount": amount, "currency": "GBP", "created": "2026-11-01T09:00:00Z",
            "description": f"SYNTHETIC SHOP {i}", "settled": settled, "merchant": None, **extra}


class FakeTransport:
    def __init__(self, routes, status=200, ctype="application/json"):
        self.routes, self.status, self.ctype, self.calls = routes, status, ctype, []

    def __call__(self, method, path, headers):
        self.calls.append((method, path, headers))
        body = self.routes(path) if callable(self.routes) else self.routes
        return self.status, self.ctype, json.dumps(body).encode()


class MonzoTests(unittest.TestCase):
    def test_request_shape_is_read_only_and_exact(self):
        t = FakeTransport({"accounts": []})
        monzo.request("accounts", TOKEN, t)
        method, path, headers = t.calls[0]
        self.assertEqual((method, path), ("GET", "/accounts"))
        self.assertEqual(headers["Authorization"], "Bearer " + TOKEN)
        self.assertEqual(set(headers), {"Authorization", "Accept", "Accept-Encoding"})
        t = FakeTransport({"balance": 1, "currency": "GBP"})
        monzo.request("balance", TOKEN, t, account_id=ACC)
        self.assertEqual(t.calls[0][1], "/balance?account_id=" + ACC)

    def test_parameter_validation(self):
        t = FakeTransport({})
        for args in ({"account_id": "x"}, {"account_id": ACC, "limit": 0}, {"account_id": ACC, "limit": 101},
                     {"account_id": ACC, "since": "yesterday"}, {"account_id": ACC, "before": "tx_0000000000AB"}):
            with self.assertRaises(ValueError):
                monzo.request("transactions", TOKEN, t, **args)
        with self.assertRaises(ValueError):
            monzo.request("delete_pot", TOKEN, t, account_id=ACC)
        self.assertEqual(t.calls, [])
        monzo.request("transactions", TOKEN, FakeTransport({"transactions": []}),
                      account_id=ACC, since="2026-11-01T00:00:00Z", before="2026-11-02T00:00:00.5Z", limit=100)

    def test_missing_or_invalid_token_is_not_configured_never_simulated(self):
        with self.assertRaisesRegex(monzo.MonzoError, "NOT_CONFIGURED"):
            monzo.request("accounts", None, FakeTransport({}))
        with self.assertRaises(ValueError):
            monzo.request("accounts", "short", FakeTransport({}))

    def test_http_errors_and_bad_content_do_not_leak_bodies(self):
        with self.assertRaisesRegex(monzo.MonzoError, "MONZO_HTTP_401") as ctx:
            monzo.request("accounts", TOKEN, FakeTransport({"secret": "SENSITIVE"}, status=401))
        self.assertNotIn("SENSITIVE", str(ctx.exception))
        with self.assertRaisesRegex(monzo.MonzoError, "INVALID_RESPONSE"):
            monzo.request("accounts", TOKEN, FakeTransport({}, ctype="text/html"))

    def test_normalisation_signs_status_and_declines(self):
        out = monzo.normalize_transaction(tx(1, amount=-1234))
        self.assertEqual((out["minor"], out["status"], out["date"], out["currency"]), (-1234, "BOOK", "2026-11-01", "GBP"))
        self.assertEqual(monzo.normalize_transaction(tx(2, settled=""))["status"], "PDNG")
        self.assertEqual(monzo.normalize_transaction(tx(3, amount=0, decline_reason="INSUFFICIENT_FUNDS"))["status"], "DECL")
        named = monzo.normalize_transaction(tx(4, merchant={"name": "Tesco"}))
        self.assertEqual(named["description"], "Tesco")
        with self.assertRaises(ValueError):
            monzo.normalize_transaction({"id": "x", "amount": "12.50", "created": "2026-11-01T00:00:00Z"})
        self.assertEqual(monzo.normalize_balance({"balance": 12345, "currency": "GBP", "spend_today": -200})["minor"], 12345)

    def test_pagination_dedupes_excludes_declines_and_stops(self):
        pages = {None: [tx(i) for i in range(1, 101)], tx(100)["id"]: [tx(100), tx(101), tx(102, amount=0, decline_reason="X")]}

        def routes(path):
            cursor = None
            if "since=" in path:
                cursor = path.split("since=")[1].split("&")[0]
            return {"transactions": pages[cursor]}

        t = FakeTransport(routes)
        result = monzo.fetch_transactions(TOKEN, ACC, t)
        self.assertEqual(len(result), 101 + 0)            # 100 + tx101; tx100 de-duplicated, decline excluded
        self.assertEqual(len(t.calls), 2)
        with_declines = monzo.fetch_transactions(TOKEN, ACC, FakeTransport(routes), include_declined=True)
        self.assertEqual(len(with_declines), 102)

    def test_runaway_pagination_is_bounded(self):
        counter = iter(range(10**6))
        t = FakeTransport(lambda path: {"transactions": [tx(next(counter)) for _ in range(100)]})
        with self.assertRaisesRegex(monzo.MonzoError, "PAGE_LIMIT_REACHED"):
            monzo.fetch_transactions(TOKEN, ACC, t)
        self.assertEqual(len(t.calls), monzo.MAX_PAGES)

    def test_history_coverage_follows_the_five_minute_rule(self):
        start = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)
        self.assertEqual(monzo.coverage(start, start + timedelta(seconds=299)), "FULL_HISTORY")
        self.assertEqual(monzo.coverage(start, start + timedelta(seconds=301)), "LAST_90_DAYS")
        self.assertEqual(monzo.coverage(0, 100), "FULL_HISTORY")


if __name__ == "__main__":
    unittest.main()
