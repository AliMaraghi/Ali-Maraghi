"""Single Action Gateway: typed payloads -> human approval -> policy -> budget -> adapter -> audit.

Nothing reaches an adapter except through `execute`, which requires an APPROVED proposal and
re-checks kill state, durable stop, domain, sensitivity, adapter configuration and budget at that
moment. No external adapter is registered in this release: only local record and mock adapters exist.
An adapter that is not configured yields NOT_CONFIGURED, never simulated success.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from .approvals import ApprovalBook, ApprovalError
from .budget import Budget, BudgetDenied
from .policy import KillState, Policy, enforce_durable_stop
from .schema import DOMAINS, identifier

POLICY_VERSION = "gateway-1"
MAX_TEXT = 2000
ALLOWED_SENSITIVITY = {"public", "synthetic"}


class GatewayError(PermissionError):
    pass


@dataclass(frozen=True)
class KindSpec:
    domains: frozenset
    fields: dict                       # exact field name -> python type
    adapter: str | None = None         # None = local record only
    pool: str = "core"
    provider: str = "mock"
    sku: str = "echo"
    units_field: str | None = None     # payload field carrying estimated units (int)


class MockAdapter:
    """Deterministic local stand-in. Records what it was asked; touches nothing outside memory."""
    name = "mock"

    def __init__(self, fail_times=0, actual_units=None):
        self.sent, self.fail_times, self.actual_units = [], fail_times, actual_units

    def configured(self):
        return True

    def dispatch(self, payload, idempotency_key):
        if self.fail_times > 0:
            self.fail_times -= 1
            raise RuntimeError("mock adapter failure")
        self.sent.append((idempotency_key, dict(payload)))
        units = payload.get("units", 0) if self.actual_units is None else self.actual_units
        return {"actual_units": units}


class UnconfiguredAdapter:
    configured_value = False

    def __init__(self, name):
        self.name = name

    def configured(self):
        return False

    def dispatch(self, payload, idempotency_key):          # pragma: no cover - never reachable
        raise GatewayError("NOT_CONFIGURED")


DEFAULT_KINDS = {
    "record_decision": KindSpec(frozenset(DOMAINS), {"note": str}),
    "mock_notify": KindSpec(frozenset(DOMAINS), {"message": str}, adapter="mock"),
    # Real-adapter kinds: with no adapter bound they resolve to NOT_CONFIGURED, never simulated success.
    "telegram_notify": KindSpec(frozenset({"personal", "opportunity"}), {"text": str}, adapter="telegram"),
    "gmail_draft": KindSpec(frozenset({"personal"}), {"to": str, "subject": str, "body": str}, adapter="gmail"),
    "laptop_browser_task": KindSpec(frozenset({"personal", "opportunity"}), {"purpose": str, "url": str, "steps_json": str}, adapter="laptop_browser"),
    "outlook_draft": KindSpec(frozenset({"personal"}), {"to": str, "subject": str, "body": str}, adapter="outlook"),
    # adapter=None: local record only. A-2's Planner->Researcher->Executor->Critic pipeline
    # proposes a draft here; nothing is ever posted, published or sent automatically.
    "research_brief_proposal": KindSpec(frozenset({"opportunity"}), {"topic": str, "draft": str, "critic_notes": str}),
}


class ActionGateway:
    def __init__(self, ledger, approvals: ApprovalBook, budget: Budget, adapters=None, kinds=None,
                 kill_state=KillState.RUNNING):
        self.ledger, self.approvals, self.budget = ledger, approvals, budget
        self.adapters = dict(adapters or {})
        self.kinds = dict(kinds or DEFAULT_KINDS)
        self.kill_state = kill_state

    # ---- typed payloads ----------------------------------------------------
    def validate(self, kind, domain, payload, sensitivity="synthetic"):
        spec = self.kinds.get(kind)
        if spec is None:
            raise GatewayError("UNKNOWN_ACTION_KIND")
        if domain not in spec.domains:
            raise GatewayError("DOMAIN_DENIED")
        if sensitivity not in ALLOWED_SENSITIVITY:
            raise GatewayError("PRIVATE_DATA_UNSUPPORTED")
        if not isinstance(payload, dict) or set(payload) != set(spec.fields):
            raise GatewayError("PAYLOAD_FIELDS_MISMATCH")
        for name, expected in spec.fields.items():
            value = payload[name]
            if type(value) is not expected:
                raise GatewayError("PAYLOAD_TYPE_MISMATCH")
            if expected is str and not 0 < len(value) <= MAX_TEXT:
                raise GatewayError("PAYLOAD_TEXT_BOUNDS")
            if expected is int and not 0 <= value <= 10**9:
                raise GatewayError("PAYLOAD_INT_BOUNDS")
        return spec

    def submit(self, proposal_id, domain, kind, proposer, payload, evidence_ids, commentary=None,
               sensitivity="synthetic"):
        self.validate(kind, domain, payload, sensitivity)
        return self.approvals.propose(proposal_id, domain, kind, proposer, payload, evidence_ids, commentary)

    # ---- execution ---------------------------------------------------------
    def _audit(self, proposal_id, event, domain, detail):
        self.ledger._append(identifier(f"gw.{proposal_id}.{event}"[:80]), "decision", domain,
                            {"proposal": proposal_id, "event": event, "policy_version": POLICY_VERSION, **detail})

    def _refuse(self, proposal_id, domain, code):
        with self.ledger.transaction():
            self._audit(proposal_id, "refused." + code.lower()[:24], domain, {"reason": code})
        raise GatewayError(code)

    def execute(self, proposal_id):
        view = self.approvals.view(proposal_id)
        domain, kind = view["domain"], view["kind"]
        if view["state"] != "APPROVED":
            raise GatewayError("NOT_APPROVED")
        spec = self.validate(kind, domain, view["payload"])
        if self.kill_state in {KillState.FREEZE_INGRESS, KillState.DISABLE_EGRESS, KillState.STOP_EXECUTION,
                               KillState.REVOKE_CREDENTIALS}:
            self._refuse(proposal_id, domain, self.kill_state.value)
        try:
            enforce_durable_stop(self.ledger)
        except PermissionError:
            self._refuse(proposal_id, domain, "DURABLE_STOP_ACTIVE")

        adapter = None
        if spec.adapter is not None:
            adapter = self.adapters.get(spec.adapter)
            if adapter is None or not adapter.configured():
                self._refuse(proposal_id, domain, "NOT_CONFIGURED")

        reservation = None
        if adapter is not None:
            attempts = self.ledger.db.execute("SELECT COUNT(*) FROM budget_reservations WHERE key LIKE ?",
                                              (f"exec.{proposal_id}%",)).fetchone()[0]
            first = f"exec.{proposal_id}"
            key = first if attempts == 0 else f"{first}.r{attempts}"
            units = view["payload"].get(spec.units_field, 0) if spec.units_field else 0
            try:
                if attempts == 0:
                    self.budget.reserve(key, spec.pool, spec.provider, spec.sku, units)
                else:
                    self.budget.reserve(key, "retry", spec.provider, spec.sku, units, retry_of=first)
            except BudgetDenied as exc:
                self._refuse(proposal_id, domain, "BUDGET_" + str(exc).split(":")[0])
            reservation = key
            try:
                result = adapter.dispatch(view["payload"], key)
            except Exception:
                self.budget.release(reservation)
                with self.ledger.transaction():
                    self._audit(proposal_id, "dispatch_failed." + str(attempts), domain, {"adapter": spec.adapter})
                raise GatewayError("DISPATCH_FAILED") from None
            self.budget.settle(reservation, int(result.get("actual_units", units)))

        try:
            self.approvals.execute(proposal_id, Policy(domain=domain, kill_state=self.kill_state))
        except ApprovalError as exc:
            raise GatewayError(str(exc)) from None
        with self.ledger.transaction():
            self._audit(proposal_id, "dispatched", domain,
                        {"adapter": spec.adapter or "local_record", "reservation": reservation})
        return "EXECUTED"
