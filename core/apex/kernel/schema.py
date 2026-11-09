"""Strict contracts for public/synthetic research; private dossiers are unsupported."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal
import json
import re

Domain = Literal["opportunity", "studio", "personal"]
DOMAINS = {"opportunity", "studio", "personal"}


def text(value: object, name: str, maximum: int = 2000) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError(f"Invalid {name}")
    if any(ord(c) < 32 and c not in "\n\t" for c in value):
        raise ValueError(f"Control character in {name}")
    return value.strip()


def identifier(value: object) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", value):
        raise ValueError("Invalid identifier")
    return value


def timestamp(value: object) -> datetime:
    result = datetime.fromisoformat(text(value, "timestamp", 80).replace("Z", "+00:00"))
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("Timezone required")
    return result


def fields(value: object, required: set[str], optional: set[str] | None = None) -> dict:
    if not isinstance(value, dict) or not required <= value.keys() or value.keys() - required - (optional or set()):
        raise ValueError("Missing or unknown contract fields")
    return value


def items(value: object, name: str, maximum: int = 100) -> list:
    if not isinstance(value, list) or len(value) > maximum:
        raise ValueError(f"Invalid {name}")
    return value


def strict_json(raw: str) -> object:
    def pairs(values):
        out = {}
        for key, value in values:
            if key in out:
                raise ValueError("Duplicate JSON key")
            out[key] = value
        return out
    def nonfinite(_):
        raise ValueError("Nonfinite JSON number")
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=nonfinite)


@dataclass(frozen=True)
class Hypothesis:
    id: str
    mechanism: str
    prediction: str
    falsifier: str

    @classmethod
    def parse(cls, value):
        d = fields(value, {"id", "mechanism", "prediction", "falsifier"})
        return cls(identifier(d["id"]), *(text(d[k], k) for k in ("mechanism", "prediction", "falsifier")))


@dataclass(frozen=True)
class Claim:
    id: str
    statement: str
    kind: str
    evidence_ids: tuple[str, ...]

    @classmethod
    def parse(cls, value):
        d = fields(value, {"id", "statement", "kind", "evidence_ids"})
        if d["kind"] not in {"observation", "hypothesis", "inference", "prediction", "preference"}:
            raise ValueError("Invalid claim kind")
        refs = tuple(identifier(x) for x in items(d["evidence_ids"], "references"))
        if len(refs) != len(set(refs)):
            raise ValueError("Duplicate evidence reference")
        return cls(identifier(d["id"]), text(d["statement"], "claim"), d["kind"], refs)


@dataclass(frozen=True)
class Evidence:
    id: str
    claim_id: str
    source_uri: str
    publisher: str
    independence_group: str
    retrieved_at: str
    expires_at: str
    artifact: str
    sha256: str
    excerpt: str
    method: str
    synthetic: bool
    stance: str
    domain: str
    sensitivity: str

    @classmethod
    def parse(cls, value):
        d = fields(value, set(cls.__dataclass_fields__))
        if type(d["synthetic"]) is not bool:
            raise ValueError("Synthetic must be boolean")
        if d["method"] not in {"primary_document", "observation", "model_output"}:
            raise ValueError("Invalid evidence method")
        if d["stance"] not in {"supports", "refutes"} or d["domain"] not in DOMAINS:
            raise ValueError("Invalid evidence classification")
        if d["sensitivity"] not in {"public", "synthetic"}:
            raise ValueError("Private data requires a separate authorized encrypted store")
        if d["sensitivity"] == "synthetic" and not d["synthetic"]:
            raise ValueError("Synthetic classification mismatch")
        for k in ("id", "claim_id", "independence_group"):
            identifier(d[k])
        for k in ("source_uri", "publisher", "artifact", "excerpt"):
            text(d[k], k, 8000 if k == "excerpt" else 2000)
        timestamp(d["retrieved_at"]); timestamp(d["expires_at"])
        if not isinstance(d["sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", d["sha256"]):
            raise ValueError("Invalid SHA-256")
        return cls(**d)


@dataclass(frozen=True)
class Case:
    id: str
    domain: str
    problem: str
    assumptions: tuple[str, ...]
    baseline: str
    hypotheses: tuple[Hypothesis, ...]
    claims: tuple[Claim, ...]
    evidence: tuple[Evidence, ...]
    neglected_need: str
    second_order_effect: str
    smallest_test: str

    @classmethod
    def parse(cls, value):
        d = fields(value, set(cls.__dataclass_fields__))
        if d["domain"] not in DOMAINS:
            raise ValueError("Unsupported domain")
        hs = tuple(Hypothesis.parse(x) for x in items(d["hypotheses"], "hypotheses", 8))
        cs = tuple(Claim.parse(x) for x in items(d["claims"], "claims"))
        es = tuple(Evidence.parse(x) for x in items(d["evidence"], "evidence"))
        for collection in (hs, cs, es):
            if len({x.id for x in collection}) != len(collection):
                raise ValueError("Duplicate identifier")
        return cls(identifier(d["id"]), d["domain"], text(d["problem"], "problem"),
                   tuple(text(x, "assumption") for x in items(d["assumptions"], "assumptions", 30)),
                   text(d["baseline"], "baseline"), hs, cs, es,
                   *(text(d[k], k) for k in ("neglected_need", "second_order_effect", "smallest_test")))
