"""Universal Agent Contract: validation of agent outputs. Offline only; no model or network calls."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

CLAIM_KINDS = ("fact", "inference", "hypothesis")
UNTRUSTED_SOURCES = ("email", "web", "feed", "file", "mcp")


class ContractError(ValueError):
    """Raised when an agent output does not satisfy the contract."""


@dataclass(frozen=True)
class Claim:
    text: str
    kind: str
    evidence_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ContractError("claim text is empty")
        if self.kind not in CLAIM_KINDS:
            raise ContractError(f"claim kind must be one of {CLAIM_KINDS}")
        if self.kind == "fact" and not self.evidence_ids:
            raise ContractError("a fact claim must cite at least one evidence id")


@dataclass(frozen=True)
class AgentOutput:
    task_id: str
    agent_id: str
    claims: tuple[Claim, ...]
    risks: tuple[str, ...]
    unknowns: tuple[str, ...]
    confidence: float
    evidence: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.task_id or not self.agent_id:
            raise ContractError("task_id and agent_id are required")
        if not 0.0 <= self.confidence <= 1.0:
            raise ContractError("confidence must be between 0 and 1")


def parse_output(payload: dict[str, Any]) -> AgentOutput:
    """Build a validated AgentOutput from a plain dict, rejecting malformed input."""
    if not isinstance(payload, dict):
        raise ContractError("payload must be an object")
    required = ("task_id", "agent_id", "claims", "risks", "unknowns", "confidence")
    missing = [key for key in required if key not in payload]
    if missing:
        raise ContractError(f"missing fields: {', '.join(missing)}")
    claims = []
    for raw in payload["claims"]:
        if not isinstance(raw, dict):
            raise ContractError("each claim must be an object")
        claims.append(Claim(
            text=str(raw.get("text", "")),
            kind=str(raw.get("kind", "")),
            evidence_ids=tuple(str(x) for x in raw.get("evidence_ids", [])),
        ))
    try:
        confidence = float(payload["confidence"])
    except (TypeError, ValueError) as exc:
        raise ContractError("confidence must be a number") from exc
    return AgentOutput(
        task_id=str(payload["task_id"]),
        agent_id=str(payload["agent_id"]),
        claims=tuple(claims),
        risks=tuple(str(x) for x in payload["risks"]),
        unknowns=tuple(str(x) for x in payload["unknowns"]),
        confidence=confidence,
        evidence=tuple(str(x) for x in payload.get("evidence", [])),
    )


def wrap_untrusted(source: str, content: str) -> dict[str, str]:
    """Mark external content as data. It is never treated as an instruction."""
    if source not in UNTRUSTED_SOURCES:
        raise ContractError(f"unknown untrusted source: {source}")
    return {"role": "data", "source": source, "content": content, "instructions": "none"}
