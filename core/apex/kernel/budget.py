"""Effective-dated cost registry and atomic budget reservation (integer minor units, GBP).

Default is zero paid budget: until an operator sets caps AND registers a fresh price, only
explicitly registered zero-price (mock) SKUs can be reserved. Unknown, not-yet-effective or stale
prices block paid execution. Reservation is atomic (single write transaction); retries draw on
their own pool. This module never calls a provider; it only decides and records.
"""
from __future__ import annotations

import time

from .schema import identifier

POOLS = ("core", "intelligence", "studio", "retry")
PERIODS = ("day", "week", "month")
STALE_AFTER = 30 * 24 * 3600
CURRENCY = "GBP"


class BudgetDenied(PermissionError):
    pass


def window_start(period, now):
    t = time.gmtime(now)
    midnight = now - (t.tm_hour * 3600 + t.tm_min * 60 + t.tm_sec)
    if period == "day":
        return midnight
    if period == "week":
        return midnight - t.tm_wday * 86400
    return midnight - (t.tm_mday - 1) * 86400


class Budget:
    def __init__(self, ledger, clock=time.time):
        self.ledger, self.clock = ledger, clock
        ledger.db.executescript("""
            CREATE TABLE IF NOT EXISTS cost_registry (
              provider TEXT NOT NULL, sku TEXT NOT NULL, effective_from REAL NOT NULL,
              price_millipence INTEGER NOT NULL CHECK(price_millipence>=0), currency TEXT NOT NULL,
              source TEXT NOT NULL, verified_at REAL NOT NULL, PRIMARY KEY(provider,sku,effective_from));
            CREATE TABLE IF NOT EXISTS budget_caps (
              pool TEXT NOT NULL, period TEXT NOT NULL, cap_minor INTEGER NOT NULL CHECK(cap_minor>=0),
              PRIMARY KEY(pool,period));
            CREATE TABLE IF NOT EXISTS budget_reservations (
              key TEXT PRIMARY KEY, pool TEXT NOT NULL, provider TEXT NOT NULL, sku TEXT NOT NULL,
              units INTEGER NOT NULL, price_millipence INTEGER NOT NULL, reserved_minor INTEGER NOT NULL,
              actual_minor INTEGER, state TEXT NOT NULL, created_at REAL NOT NULL);
        """)

    # ---- operator configuration -------------------------------------------
    def set_price(self, provider, sku, price_millipence, effective_from, source, verified_at=None):
        identifier(provider), identifier(sku)
        if type(price_millipence) is not int or price_millipence < 0 or not source:
            raise ValueError("Price must be a non-negative integer (1/1000 pence) with a source")
        with self.ledger.transaction():
            self.ledger.db.execute("INSERT OR REPLACE INTO cost_registry VALUES (?,?,?,?,?,?,?)",
                                   (provider, sku, float(effective_from), price_millipence, CURRENCY, source,
                                    float(verified_at if verified_at is not None else self.clock())))

    def set_cap(self, pool, period, cap_minor):
        if (pool not in POOLS and pool != "global") or period not in PERIODS or type(cap_minor) is not int or cap_minor < 0:
            raise ValueError("Invalid cap")
        with self.ledger.transaction():
            self.ledger.db.execute("INSERT OR REPLACE INTO budget_caps VALUES (?,?,?)", (pool, period, cap_minor))

    # ---- decision ---------------------------------------------------------
    def price(self, provider, sku, now):
        row = self.ledger.db.execute(
            "SELECT price_millipence,verified_at FROM cost_registry WHERE provider=? AND sku=? AND effective_from<=? "
            "ORDER BY effective_from DESC LIMIT 1", (provider, sku, now)).fetchone()
        if row is None:
            raise BudgetDenied("UNKNOWN_PRICE")
        if row[0] > 0 and now - row[1] > STALE_AFTER:
            raise BudgetDenied("STALE_PRICE")
        return row[0]

    def spent(self, pool, period, now):
        since = window_start(period, now)
        where = "" if pool == "global" else "AND pool=?"
        args = (since,) if pool == "global" else (since, pool)
        return self.ledger.db.execute(
            "SELECT COALESCE(SUM(CASE WHEN state='SETTLED' THEN MAX(actual_minor,0) "
            "WHEN state='RESERVED' THEN reserved_minor ELSE 0 END),0) "
            "FROM budget_reservations WHERE created_at>=? " + where, args).fetchone()[0]

    def reserve(self, key, pool, provider, sku, units, retry_of=None):
        if len(identifier(key)) > 48:
            raise ValueError("Reservation key too long")
        if pool not in POOLS or type(units) is not int or units < 0:
            raise ValueError("Invalid reservation request")
        if (pool == "retry") != (retry_of is not None):
            raise ValueError("Retries must use the retry pool and name the original key")
        now = self.clock()
        with self.ledger.transaction():
            prior = self.ledger.db.execute(
                "SELECT pool,provider,sku,units,state FROM budget_reservations WHERE key=?", (key,)).fetchone()
            if prior:
                if prior[:4] != (pool, provider, sku, units):
                    raise ValueError("Idempotency key conflicts with prior reservation")
                return prior[4]
            price = self.price(provider, sku, now)
            cost = -(-units * price // 1000)                      # ceiling to whole pence
            if cost > 0:
                if self.ledger.db.execute("SELECT COUNT(*) FROM budget_caps WHERE pool=?", (pool,)).fetchone()[0] == 0:
                    raise BudgetDenied("NO_CAP_CONFIGURED")           # zero paid budget by default
                for scope in (pool, "global"):
                    for period in PERIODS:
                        cap = self.ledger.db.execute("SELECT cap_minor FROM budget_caps WHERE pool=? AND period=?",
                                                     (scope, period)).fetchone()
                        if cap is not None and self.spent(scope, period, now) + cost > cap[0]:
                            raise BudgetDenied(f"CAP_EXCEEDED:{scope}:{period}")
            self.ledger.db.execute("INSERT INTO budget_reservations VALUES (?,?,?,?,?,?,?,NULL,'RESERVED',?)",
                                   (key, pool, provider, sku, units, price, cost, now))
            self.ledger._append(identifier(("bud." + key)[:80]), "decision", "personal",
                                {"event": "reserved", "pool": pool, "reserved_minor": cost, "currency": CURRENCY,
                                 "retry_of": retry_of})
        return "RESERVED"

    def settle(self, key, actual_units):
        if type(actual_units) is not int or actual_units < 0:
            raise ValueError("Invalid actual usage")
        with self.ledger.transaction():
            row = self.ledger.db.execute(
                "SELECT price_millipence,reserved_minor,state,pool FROM budget_reservations WHERE key=?", (key,)).fetchone()
            if row is None or row[2] != "RESERVED":
                raise BudgetDenied("NOT_RESERVED")
            actual = -(-actual_units * row[0] // 1000)
            self.ledger.db.execute("UPDATE budget_reservations SET actual_minor=?, state='SETTLED' WHERE key=?", (actual, key))
            self.ledger._append(identifier(("bud." + key + ".s")[:80]), "decision", "personal",
                                {"event": "settled", "pool": row[3], "reserved_minor": row[1], "actual_minor": actual,
                                 "overrun": actual > row[1]})
        return actual

    def release(self, key):
        with self.ledger.transaction():
            row = self.ledger.db.execute("SELECT state FROM budget_reservations WHERE key=?", (key,)).fetchone()
            if row is None or row[0] != "RESERVED":
                raise BudgetDenied("NOT_RESERVED")
            self.ledger.db.execute("UPDATE budget_reservations SET state='RELEASED' WHERE key=?", (key,))
            self.ledger._append(identifier(("bud." + key + ".r")[:80]), "decision", "personal",
                                {"event": "released"})
