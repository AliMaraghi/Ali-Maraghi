"""Multi-domain scaffolding, single-domain activation (mission 2026-11-15). Three domain
modules (bills, email, calendar) are built and tested with synthetic fixtures; exactly ONE
runs in agents_runner.py --once for the 21-day measurement window. The other two are STAGED:
code exists, tests exist, they are not executed by the scheduler.

This mirrors core/apex/agents_governing.FROZEN's design (a frozen system is code that stays,
not code that is deleted) but is deliberately a SEPARATE mechanism, not a reuse of FROZEN -
FROZEN marks systems that are explicitly out of scope for this whole mission (the digital
twin, marketing funnel, etc); staged domains are explicitly IN scope, just not active yet,
and the 21-day unfreeze condition in docs/ACTIVE_SYSTEM.md governs when a staged one may
become active - that is a decision this router does not make for itself."""
from __future__ import annotations

from enum import Enum


class Domain(Enum):
    BILLS = "bills"
    EMAIL = "email"
    CALENDAR = "calendar"


ACTIVE_DOMAIN = Domain.BILLS   # hardcoded per the mission - not read from config, not inferred


def is_active(domain: Domain) -> bool:
    return domain == ACTIVE_DOMAIN


def skip_message(domain: Domain) -> str:
    return f"[SKIPPED] Domain {domain.value} is STAGED. Active domain is {ACTIVE_DOMAIN.value}"
