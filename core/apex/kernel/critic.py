"""Deterministic adversarial checks separate from candidate construction.

This is an automated checklist, not an independent scientific reviewer.
"""
import re
from .schema import Case


def tokens(value):
    return set(re.findall(r"\w+", value.casefold()))


def critique(case: Case, inspected: list[dict]) -> list[dict]:
    findings = []
    def add(code, target, detail):
        findings.append({"code": code, "target": target, "detail": detail, "status": "OPEN"})
    if len(case.hypotheses) < 2:
        add("INSUFFICIENT_ALTERNATIVES", case.id, "Supply at least two different causal mechanisms.")
    for i, left in enumerate(case.hypotheses):
        for right in case.hypotheses[i + 1:]:
            a, b = tokens(left.mechanism), tokens(right.mechanism)
            if len(a & b) / max(1, len(a | b)) >= .75 or tokens(left.prediction) == tokens(right.prediction):
                add("DUPLICATE_ALTERNATIVES", right.id, "Renaming or rewording the same mechanism is insufficient.")
    if not case.assumptions:
        add("ASSUMPTIONS_MISSING", case.id, "State what would make the proposed problem framing wrong.")
    if not case.claims:
        add("CLAIMS_MISSING", case.id, "Supply claims that can be checked against source artifacts.")
    records = {e.id: e for e in case.evidence}
    checks = {e["id"]: e for e in inspected}
    known_claims = {c.id for c in case.claims}
    for e in case.evidence:
        if e.claim_id not in known_claims:
            add("ORPHAN_EVIDENCE", e.id, "Evidence does not refer to a known claim.")
    for claim in case.claims:
        relevant = []
        for ref in claim.evidence_ids:
            if ref not in records:
                add("UNKNOWN_EVIDENCE", claim.id, "A citation identifier has no source record.")
            elif records[ref].claim_id != claim.id:
                add("MISATTRIBUTED_EVIDENCE", claim.id, "Citation belongs to another claim.")
            elif checks[ref]["eligible_for_review"]:
                relevant.append(records[ref])
        if claim.kind in {"observation", "inference"} and not relevant:
            add("UNSUPPORTED_CLAIM", claim.id, "No eligible source artifact supports review of this claim.")
        if any(e.stance == "refutes" for e in relevant):
            add("CONTRARY_EVIDENCE", claim.id, "Contrary evidence must be resolved or uncertainty retained.")
        support = [e for e in relevant if e.stance == "supports"]
        groups = {e.independence_group for e in support}
        # Duplicate content or hosts cannot become independent through relabelling.
        hashes = {e.sha256 for e in support}
        from urllib.parse import urlsplit
        hosts = {urlsplit(e.source_uri).hostname for e in support}
        if claim.kind == "inference" and min(len(groups), len(hashes), len(hosts)) < 2:
            add("INDEPENDENCE_NOT_ESTABLISHED", claim.id, "An inference needs corroboration; source labels alone prove no independence.")
    for check in inspected:
        for issue in check["issues"]:
            add(issue, check["id"], "Evidence cannot be used as a verified finding.")
    return findings
