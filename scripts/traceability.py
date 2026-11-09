"""Validate private source traceability. This is not a semantic acceptance test.

Every nonblank source line is retained by reference and byte hash, including
historical wording, gaps, framing and delimiters. Original text is not copied
to this generated registry. Only the fixed five handoff sources are read.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HANDOFF = "docs/apex_handoff_20261109/"
REGISTRY = "docs/apex_status/REQUIREMENTS.json"
VERSION = "apex-traceability-1"
SOURCES = {
    "M": ("APEX_4_4_FINAL_MASTER_MANIFESTO.md", "3947a6b676c01ac642e95020303b1274c750b7a0df59519efccf1f6a8b9c1bcd"),
    "C": ("MISSION_CONTRACT.md", "4839c77c5cca83d88682db8df378fec73e31e266786d20e653eaf795027a9b02"),
    "A": ("APEX_4_4_ACCEPTANCE_GATE_FA.md", "6b2111a9ab264319e6465c9a8c9cda4b8f5ef0c59a163a90d73536ee8cac9ea9"),
    "V": ("APEX_4_4_ACCEPTANCE_MATRIX.csv", "5976124277424dbfef68aec5be779750124e37eeaef70c01733790d9df8626cc"),
    "U": ("APEX_4_4_User_Supplied_Source.md", "0abf0eb4d6500991e4fa1e646531ac38eee7da4d72ff7b7770e38cb5049718ba"),
}
DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
# title; missing prerequisites; future acceptance scenario. No completion is
# inferred from a file name or from passing the traceability tests.
SECTIONS = [
    ("Governance, ownership, infrastructure, budget and recovery", "Authorized isolated staging; tested restore target; production authorization", "Deny unapproved spend/action; exercise four stop stages and restoration; prove least privilege separately"),
    ("Open-world research, provenance, source discovery and weak signals", "Authorized primary-source retrieval and independent observations", "Replay sources with provenance, freshness, contradictions and false-alert metrics against a manual checklist"),
    ("Identity, style and stated/observed/inferred memory", "Consented identity data, approved style examples and private storage", "Test correction, deletion and consent; blindly grade ten varied style samples without invented memories"),
    ("Platform-specific publishing and measured audience targets", "Official platform capabilities, approved media and publication authorization", "Export approved platform variants and verify rights/permissions; measure actual outcomes without guaranteed growth"),
    ("Original creative signature, durable thesis and cultural legacy", "Owner-approved style, licensed media and independent human reviewers", "Blindly review originality, evidence, dramatic structure, sound, visual coherence and long-term relevance"),
    ("Planner, contracts, evidence graph and deterministic gateway", "Typed contracts, independent semantic review and scoped policy", "Reject malformed claims, invented references, evidence instructions and unsafe actions; retain contradictions and uncertainty"),
    ("Respectful social intelligence and permitted professional monitoring", "Domain consent, official capabilities, privacy isolation; no connected accounts", "Exercise consent, refusal, stop-contact, expiry, account permissions and private/professional separation"),
    ("Open-world opportunity registry, economics and outcomes", "Primary sources, external validation and explicit authority for outreach", "Assess ten real opportunities and independently check three; document demand, costs, eligibility, uncertainty and smallest experiment"),
    ("Eighteen specialist roles with executable capability boundaries", "Role implementations and evaluators; incomplete original wording remains SOURCE GAP", "Invoke each role and test contracts, positive/negative boundaries and measured quality; names do not count as implementation"),
    ("UK personal finance, benefits, tax and housing", "Current official rules, independently checked calculations and domain consent", "Test dated deterministic scenarios for benefits, tax and affordability; no account access or money movement by default"),
    ("Cost accounting, failures, trust, quality gates and metrics", "Trusted prices/invoices for paid operations; controls and recovery evidence", "Exercise zero budget, unknown costs, capped retries, regression and recovery; separate paid API cost from human effort"),
    ("Privacy, lawful purpose, data rights and employer separation", "Approved purposes, retention/access control and appropriate legal review", "Test minimisation, deletion, retention and domain denial; do not claim legal compliance from unit tests"),
    ("Isolated personal dossier, keys and access audit", "Dedicated encrypted storage, separate key management and explicit consent", "Test isolation, access audit, retention, deletion and denial to public-content tools"),
    ("Autonomy, Decision Twin and manageable approvals", "Narrow approved capabilities and revocable grants", "Test approval expiry/revocation, silence as non-consent, daily decision limit and low-energy mode"),
    ("Foresight, threat-to-opportunity and missed-opportunity learning", "Independent dated observations and held-out outcome labels", "Evaluate three cases with contrary explanations, false positives, missed signals and independently checked outcomes"),
    ("Publishing queues, official access and London timezone", "Official accounts, explicit publication authorization and staging queue", "Test DST, duplicate jobs, bounded retries, rate limits, revocation and official sandbox receipts"),
    ("Global growth, language mix, cultural value and revenue scenarios", "Actual audience observations, rights and measured commercial outcomes", "Separate pessimistic/base/optimistic targets from realized reach/revenue; check conflicts and rights"),
    ("Measured evolution, independent evaluation and rollback", "Independent evaluation cases, versioned experiments and controlled promotion", "Use disjoint unseen cases, reject quality/safety regression, canary changes and restore previous version with evidence"),
    ("Real audiovisual production, authorized assets and export quality", "Actual authorized Lagos/Portugal footage, rights, audio, renderer and owner review", "Produce playable 60-90 second film with sound/subtitles, source/cost report and human audiovisual review"),
]
CANDIDATES = {
    0: ["kernel/policy.py", "kernel/memory.py"], 1: ["rss.py", "kernel/evidence.py"],
    4: ["domains.py"], 5: ["kernel/schema.py", "kernel/evidence.py", "kernel/critic.py", "kernel/engine.py", "kernel/policy.py"],
    6: ["domains.py", "kernel/policy.py"], 7: ["domains.py", "kernel/engine.py"],
    10: ["kernel/policy.py"], 11: ["kernel/policy.py"], 13: ["kernel/policy.py"],
    14: ["kernel/engine.py"], 17: ["kernel/memory.py"], 18: ["domains.py"],
}
APPENDICES = {
    "HEALTH": (310, 343, "Health, longevity, exercise, skin, recovery and behavioral ergonomics", "Consented records, medical evidence review and private storage", "Test human/animal evidence distinctions, uncertainty, safe escalation and denial of health-to-public leakage"),
    "KERNEL": (344, 362, "Constitutional kernel and domain reasoning boundaries", "Scoped domain controls and independent evaluation", "Test authority separation, uncertainty, claim types and cross-domain denial"),
    "PWA": (363, 370, "Secure iPhone command centre", "Authenticated application, scoped API, private cache and notifications", "Test session expiry/revocation, authorization, reconnect, rate limits and private-data minimisation"),
    "ML": (371, 376, "Machine learning, prediction and evaluation", "Real labeled datasets and independent train/validation/test split", "Record feature/dataset/model versions, baseline/holdout metrics, leakage, drift, calibration, fairness and rollback"),
    "ORIGINALITY": (377, 380, "Originality, cultural signature and ownership", "Approved style and independent reviewers", "Grade thesis, rhythm, coherence, rights and rejection of unsupported human-likeness claims"),
    "PRESERVATION": (381, 390, "Source preservation, precedence and non-deletion", "Immutable hashes, conflict and source-gap register", "Recompute hashes and retain every source unit; reject invented historical text"),
    "ACCEPTANCE": (391, 404, "Nine non-removable missions and global gates", "Independent evidence for each A01-A09 and G0-G7", "Assess every mission separately; no aggregate score may hide a critical missing capability"),
    "BLOCKERS": (405, 412, "Operational honesty and bounded alternatives", "Observable failure evidence and permitted next action", "Report exact blockers, alternatives, actual costs and remaining work without fabricated completion"),
}
ROLES = ["World Monitor", "Periodic Critic", "Strategic Interlocutor", "Temporal Mirrors", "Entropy Analyst", "Original Content Factory", "Legacy Tracker", "Silence and Attention Guardian", "Social Signal Analyst", "Reverse Prospection", "Semantic Gap Hunter", "Evidence and Adversarial Verifier", "Opportunity/CFO Analyst", "Cross-Domain Integrator", "Video Producer", "Polyglot Translator", "Platform Router", "Viral Detector"]
SOCIAL = ["Perception", "Contextual memory", "Mutuality", "Natural expression", "Timing", "Adaptive communication", "Relationship momentum", "Personal agency", "Platform capabilities", "Permitted autonomy", "Conversation recovery", "Real-world discovery", "Boundary protection", "Outcome learning", "Consented private social scope", "Source discovery", "Permitted participation", "Private context isolation", "Verified event records", "Execution and learning"]
ACCEPTANCE = ["Original media and global signature", "Human originality and style", "Mutual social communication", "Consented private adult experiences", "Responsible operational autonomy", "Strategic foresight", "Open-world economic opportunity", "Cross-domain life support with privacy", "Controlled measurable evolution"]


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def source_data(root: Path) -> dict:
    sources = {}
    for key, (name, expected) in SOURCES.items():
        path = HANDOFF + name
        raw = (root / path).read_bytes()
        if digest(raw) != expected:
            raise ValueError("Immutable source digest mismatch: " + path)
        sources[key] = {"path": path, "sha256": expected, "lines": raw.splitlines(keepends=True)}
    return sources


def anchor(sources: dict, key: str, start: int, end: int) -> dict:
    src = sources[key]
    if not 1 <= start <= end <= len(src["lines"]):
        raise ValueError(f"Invalid source range: {key}:{start}-{end}")
    return {"path": src["path"], "start_line": start, "end_line": end,
            "sha256": digest(b"".join(src["lines"][start - 1:end])), "source_sha256": src["sha256"]}


def requirement(sources, rid, title, key, start, end, dependencies, acceptance_test, paths=(), source_gap=None):
    return {"requirement_id": rid, "summary": title, "source_anchor": anchor(sources, key, start, end),
            "implementation": [{"path": "core/apex/" + p, "relationship": "candidate_foundation_not_full_implementation"} for p in paths],
            "test": [], "evidence": [], "implementation_status": "NOT_STARTED", "acceptance_status": "NOT TESTED",
            "owner": "APEX development; founder acceptance", "version": VERSION,
            "dependencies": [dependencies], "acceptance_test": acceptance_test, "source_gap": source_gap,
            "semantic_decomposition": "Exact source clause remains authoritative; full acceptance is not established"}


def build(root: Path = ROOT) -> dict:
    sources = source_data(root)
    lines = {key: [s.decode("utf-8").rstrip("\r\n") for s in src["lines"]] for key, src in sources.items()}
    m = lines["M"]
    r = [requirement(sources, "FOUNDATION", "Founder mission and twelve immutable principles", "M", 1, 44,
                     "Preserved goals and evidence-backed implementation", "Assess truthful claims, mission continuity, privacy and measurable value")]
    starts = [(int(match[1]), n) for n, line in enumerate(m[:309], 1) if (match := re.match(r"^## ([0-9]+)\.", line.translate(DIGITS)))]
    if [number for number, _ in starts] != list(range(19)):
        raise ValueError("Canonical section structure changed")
    for i, (number, start) in enumerate(starts):
        end = starts[i + 1][1] - 1 if i < 18 else 309
        title, deps, test = SECTIONS[number]
        r.append(requirement(sources, f"S{number:02}", title, "M", start, end, deps, test, CANDIDATES.get(number, ())))
    for key, (start, end, title, deps, test) in APPENDICES.items():
        r.append(requirement(sources, "APP-" + key, title, "M", start, end, deps, test))
    r.extend([
        requirement(sources, "APP-SIGNATURE", "Authorship, approval and document limitations", "M", 413, 424, "Founder acceptance separate from authorship", "Do not represent drafted text as a legal or cryptographic signature"),
        requirement(sources, "APP-ARCHIVE", "Preserved historical working copy", "M", 425, 707, "Preserved bytes and explicit conflicts", "Retain archive without treating old claims as current authority"),
        requirement(sources, "APP-ARCHIVED-GATE", "Preserved acceptance contract", "M", 708, len(m), "Independent acceptance evidence", "Retain every acceptance criterion; never infer completion by file count"),
    ])
    for n, line in enumerate(m[:310], 1):
        match = re.match(r"^#{3,4} ([0-9]+(?:-[0-9]+)+)\.", line.translate(DIGITS))
        if not match:
            continue
        number = match[1]
        section = int(number.split("-")[0])
        end = next((j for j in range(n + 1, 311) if m[j - 1].startswith("#")), 310) - 1
        title, deps, test = SECTIONS[section]
        if number.startswith("6-1-"):
            title = SOCIAL[int(number.split("-")[-1]) - 1]
        r.append(requirement(sources, "CLAUSE-" + number, title + ": " + number, "M", n, end, deps, test, CANDIDATES.get(section, ())))
    for number in range(1, 19):
        n = next(n for n, line in enumerate(m, 1) if re.match(rf"^\| 8-{number} \|", line.translate(DIGITS)))
        gap = "SOURCE GAP: canonical 8-1..14 roles are proposed operational completion, not recovered verbatim original wording" if number <= 14 else None
        r.append(requirement(sources, f"CLAUSE-8-{number}", ROLES[number - 1], "M", n, n, SECTIONS[8][1],
                             f"Invoke {ROLES[number - 1]} on a scoped task; test contract, evidence, permissions and measured quality", source_gap=gap))
    u = [line.translate(DIGITS) for line in lines["U"]]
    for number in range(15, 21):
        n = next(n for n, line in enumerate(u, 1) if line.startswith(f"6-1-{number}."))
        end = next((j for j in range(n + 1, len(u) + 1) if re.match(r"^6-1-\d+\.", u[j - 1])), 204) - 1
        r.append(requirement(sources, f"CLAUSE-6-1-{number}", SOCIAL[number - 1], "U", n, end, SECTIONS[6][1], SECTIONS[6][2], CANDIDATES[6]))
    for section, numbers in ((12, range(1, 11)), (18, range(3, 7))):
        n = next(n for n, line in enumerate(u, 1) if f"{section}-{numbers.start} تا {section}-{numbers.stop - 1}" in line)
        for number in numbers:
            r.append(requirement(sources, f"HISTORICAL-{section}-{number}", f"Historical section {section} clause {number}: grouped wording only", "U", n, n,
                                 SECTIONS[section][1], SECTIONS[section][2], source_gap="SOURCE GAP: only grouped historical summary survives; do not invent individual original wording"))
    # Preserve individually numbered historical obligations beyond the current
    # canonical headings. Keep them staged and governed by recorded precedence.
    archived_seen = set()
    for n, line in enumerate(u, 1):
        match = re.match(r"^\s*•\s*([0-9]+-[0-9]+)(?=[.\s])", line)
        if not match or " تا " in line.split(":", 1)[0]:
            continue
        prefix = line.split(":", 1)[0]
        numbers = re.findall(r"([0-9]+-[0-9]+)", prefix)
        for number in numbers:
            if number in archived_seen:
                continue
            archived_seen.add(number)
            section = int(number.split("-")[0])
            if not 0 <= section <= 18:
                continue
            title, deps, test = SECTIONS[section]
            r.append(requirement(sources, "ARCHIVED-" + number, title + ": historical clause " + number,
                                 "U", n, n, deps, test, source_gap="Historical wording retained; canonical/current permissions govern implementation"))
    engine_roles = [
        ("Problem Discovery", "PROBLEM", "kernel/engine.py", "Identify assumptions and missing evidence; challenge the framing against observed outcomes"),
        ("Counterfactual Intelligence", "COUNTERFACTUAL", "kernel/critic.py", "Evaluate at least two substantively distinct causal hypotheses and a simple baseline; human semantic review required"),
        ("Negative-Space Discovery", "NEGATIVE-SPACE", "kernel/engine.py", "Investigate neglected needs and second-order effects with contrary sources; questions alone are not discoveries"),
        ("Independent Critic", "CRITIC", "kernel/critic.py", "Challenge source credibility, entailment, costs and failure; automated checks are not independent validation"),
        ("Empirical Performance Lab", "LAB", "kernel/lab.py", "Compare repeated measurements and unseen cases with conventional and direct-model baselines; label synthetic evidence"),
        ("Evolutionary Memory", "MEMORY", "kernel/memory.py", "Persist evaluations and failures; reject regression against current champion; reproduce rollback"),
        ("Deterministic Action Gateway", "GATEWAY", "kernel/policy.py", "Deny unsupported spend, external operations and private data; test stop states and idempotency"),
    ]
    for number, (title, code, path, test) in enumerate(engine_roles, 1):
        n = next(n for n, line in enumerate(lines["C"], 1) if line.startswith(f"{number}. {title}:"))
        r.append(requirement(sources, "RDE-" + code, title, "C", n, n,
                             "Public/synthetic inputs, trusted operator policy and independently checked outcomes", test, (path,)))
    for n, line in enumerate(m, 1):
        match = re.match(r"^### ت-([0-9]+)\.", line.translate(DIGITS))
        if match:
            end = next((j for j in range(n + 1, 344) if m[j - 1].startswith("#")), 344) - 1
            r.append(requirement(sources, "HEALTH-" + match[1], "Health appendix clause " + match[1], "M", n, end, APPENDICES["HEALTH"][3], APPENDICES["HEALTH"][4]))
    a = lines["A"]
    for number in range(1, 10):
        rid = f"A{number:02}"
        start = next(n for n, line in enumerate(a, 1) if line.startswith("### " + rid))
        end = next((j for j in range(start + 1, len(a) + 1) if a[j - 1].startswith("#")), len(a) + 1) - 1
        r.append(requirement(sources, rid, ACCEPTANCE[number - 1], "A", start, end,
                             "Independent evidence and domain-specific permissions; exact source criterion governs",
                             "Execute complete source-defined scenario and preserve independent outcomes; synthetic tests cannot establish full PASS"))
    for number in range(8):
        n = next(n for n, line in enumerate(a, 1) if line.startswith(f"| G{number} |"))
        r.append(requirement(sources, f"G{number}", f"Global acceptance gate G{number}", "A", n, n,
                             "Gate-specific evidence; development tests do not establish deployment", "Assess exact gate against reproducible evidence and independent review"))
    for key, rid, title in (("C", "MISSION", "Session mission, engine, outcomes and 21-day programme"), ("U", "SOURCE-ARCHIVE", "Historical source preservation and precedence"), ("A", "ACCEPTANCE-CONTRACT", "Acceptance freeze, evidence and scoring"), ("V", "ACCEPTANCE-MATRIX", "Immutable original acceptance matrix")):
        r.append(requirement(sources, rid, title, key, 1, len(lines[key]),
                             "Preserved source and separately recorded acceptance evidence", "Meet each source criterion and retain blocked/untested outcomes; do not replace original source status"))
    units = []
    for key, src in sources.items():
        for n, raw in enumerate(src["lines"], 1):
            if not raw.strip():
                continue
            refs = [item["requirement_id"] for item in r if item["source_anchor"]["path"] == src["path"] and item["source_anchor"]["start_line"] <= n <= item["source_anchor"]["end_line"]]
            if not refs:
                raise ValueError(f"Unmapped source unit: {key}:{n}")
            units.append({"unit_id": f"{key}-L{n:04}", "source_anchor": anchor(sources, key, n, n), "requirement_ids": refs,
                          "source_role": "immutable_reference_not_execution_authority", "semantic_review": "Exact clause retained; acceptance not established"})
    return {"schema_version": VERSION, "scope": "Private development registry; no personal archive text copied",
            "status_note": "Complete line retention is not complete semantic decomposition, implementation, independent validation or acceptance",
            "source_register": [{"key": key, "path": src["path"], "sha256": src["sha256"], "line_count": len(src["lines"])} for key, src in sources.items()],
            "requirements": r, "source_units": units}


def validate(registry: dict, root: Path = ROOT) -> list[str]:
    errors = []
    try:
        expected = build(root)
    except (OSError, ValueError) as exc:
        return [str(exc)]
    if registry.get("schema_version") != VERSION:
        errors.append("Unknown schema version")
    if registry.get("source_register") != expected["source_register"]:
        errors.append("Source register differs from immutable originals")
    if registry.get("source_units") != expected["source_units"]:
        errors.append("Source-unit coverage/hashes differ; a clause may be dropped or mislinked")
    actual = registry.get("requirements", [])
    if not isinstance(actual, list):
        return errors + ["Requirements must be a list"]
    indexed = {row.get("requirement_id"): row for row in actual if isinstance(row, dict)}
    if len(indexed) != len(actual):
        errors.append("Duplicate or malformed requirement entries")
    reference = {row["requirement_id"]: row for row in expected["requirements"]}
    if set(indexed) != set(reference):
        errors.append("Required section, clause, appendix or acceptance ID missing/unexpected")
    fields = {"requirement_id", "source_anchor", "implementation", "test", "evidence", "implementation_status", "acceptance_status", "owner", "version", "dependencies", "acceptance_test"}
    for rid, row in indexed.items():
        if not fields <= row.keys():
            errors.append(f"Missing fields: {rid}")
            continue
        if rid in reference and row["source_anchor"] != reference[rid]["source_anchor"]:
            errors.append(f"Altered source anchor: {rid}")
        if rid in reference and row.get("source_gap") != reference[rid].get("source_gap"):
            errors.append(f"Altered source gap/precedence note: {rid}")
        if row["implementation_status"] not in {"NOT_STARTED", "PROTOTYPE", "TESTED", "DEPLOYED", "BLOCKED"}:
            errors.append(f"Invalid implementation status: {rid}")
        if row["acceptance_status"] not in {"PASS", "PARTIAL", "FAIL", "BLOCKED", "NOT TESTED"}:
            errors.append(f"Invalid acceptance status: {rid}")
        if row["acceptance_status"] == "PASS" or row["implementation_status"] == "DEPLOYED":
            errors.append(f"Independent acceptance/deployment review is not supported by this registry version: {rid}")
        if not row["dependencies"] or not row["acceptance_test"] or not row["owner"]:
            errors.append(f"Missing prerequisites, acceptance scenario or owner: {rid}")
        if not all(isinstance(row[key], list) for key in ("implementation", "test", "evidence")):
            errors.append(f"Invalid mapping fields: {rid}")
            continue
        if row["implementation_status"] == "TESTED" and (not row["test"] or not row["evidence"]):
            errors.append(f"Tested status lacks test/evidence mapping: {rid}")
        for item in row["implementation"] + row["test"] + row["evidence"]:
            path = item.get("path", "") if isinstance(item, dict) else ""
            if not isinstance(path, str) or not path or Path(path).is_absolute() or ".." in Path(path).parts:
                errors.append(f"Unsafe or missing mapped path: {rid}")
            elif item.get("relationship") != "candidate_foundation_not_full_implementation" and not (root / path).is_file():
                errors.append(f"Missing implemented/test path: {rid}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", action="store_true", help="Create only when absent; never overwrite reviewed status")
    args = parser.parse_args()
    target = ROOT / REGISTRY
    if args.build:
        result = build()
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("x", encoding="utf-8") as stream:
            json.dump(result, stream, indent=2, ensure_ascii=True)
            stream.write("\n")
    result = json.loads(target.read_text(encoding="utf-8"))
    errors = validate(result)
    print(json.dumps({"status": "FAIL" if errors else "PASS_SOURCE_TRACE_ONLY", "requirements": len(result["requirements"]),
                      "source_units": len(result["source_units"]), "errors": errors, "semantic_acceptance": "NOT TESTED"}, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
