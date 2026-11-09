"""Deterministic zero-spend gateway with no external action implementation."""
from dataclasses import dataclass
from enum import Enum

from .schema import DOMAINS, identifier


class KillState(str, Enum):
    RUNNING = "RUNNING"
    FREEZE_INGRESS = "FREEZE_INGRESS"
    DISABLE_EGRESS = "DISABLE_EGRESS"
    STOP_EXECUTION = "STOP_EXECUTION"
    REVOKE_CREDENTIALS = "REVOKE_CREDENTIALS"


@dataclass(frozen=True)
class Action:
    idempotency_key: str
    kind: str
    domain: str
    estimated_pence: int = 0
    sensitivity: str = "public"


@dataclass(frozen=True)
class Policy:
    """Operator configuration; never loaded from research input or model output.

    This release has a hard zero budget. Enabling paid or external operations
    requires a reviewed implementation, not an approval flag in a document.
    """
    domain: str
    kill_state: KillState = KillState.RUNNING

    def __post_init__(self):
        if self.domain not in DOMAINS or not isinstance(self.kill_state, KillState):
            raise ValueError("Invalid operator policy")

    def authorize(self, action: Action) -> tuple[bool, str]:
        try:
            identifier(action.idempotency_key)
        except (ValueError, TypeError):
            return False, "INVALID_IDEMPOTENCY_KEY"
        if type(action.estimated_pence) is not int or action.estimated_pence < 0:
            return False, "INVALID_COST"
        if action.estimated_pence != 0:
            return False, "ZERO_BUDGET"
        if action.domain != self.domain:
            return False, "DOMAIN_DENIED"
        if not isinstance(action.sensitivity, str) or action.sensitivity not in {"public", "synthetic"}:
            return False, "PRIVATE_DATA_UNSUPPORTED"
        if self.kill_state in {KillState.FREEZE_INGRESS, KillState.STOP_EXECUTION}:
            return False, self.kill_state.value
        if action.kind != "record_decision":
            return False, "EXTERNAL_OR_UNKNOWN_ACTION_DENIED"
        return True, "LOCAL_RECORD_ONLY"

    def record(self, ledger, action: Action, result: dict):
        allowed, reason = self.authorize(action)
        if not allowed:
            raise PermissionError(reason)
        if result.get("domain") != self.domain or result.get("actions_executed") != []:
            raise PermissionError("REPORT_CONTRACT_MISMATCH")
        # No arbitrary callbacks, shell, SQL, file paths or network adapters.
        return ledger.append(action.idempotency_key, "decision", self.domain, result)
