"""Deterministic fitness scoring for target_heuristics candidates. No model grades anything.

`evaluate(program_path)` has the signature OpenEvolve expects of an evaluator. The benchmark
is real history once it exists: scout picks the owner has rated through the existing
fact/outcome store. Until there are MIN_LABELLED_OUTCOMES of those, `select_benchmark` returns
the simulated fixtures in bootstrap.py and marks the mode BOOTSTRAP, and that label travels
with every score and every proposal.

Two walls stand between a candidate and the machine. guard.py first proves the block is
data-only (no imports, calls, attributes or new names); a candidate that fails is scored -999
and never executed. Then the candidate runs in a separate interpreter (python -I -S) with a
5-second CPU limit, a memory limit, no new processes, no bytes writable to any file
(RLIMIT_FSIZE 0 - an empty file could still be created, which is why the guard comes first), sockets disabled,
and - where the kernel allows it - inside its own empty network namespace. Running the whole
lab in a container started with `--network none` adds a third wall; nothing here needs a network.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from . import guard

MIN_LABELLED_OUTCOMES = 30
POSITIVE = frozenset({"accepted", "acted_on"})
NEGATIVE = frozenset({"rejected", "ignored"})
BASELINE = Path(__file__).with_name("target_heuristics.py")
BENCHMARK_ENV = "APEX_EVOLUTION_BENCHMARK"
RUNNER = r"""
import json, resource, sys, importlib.util
cpu = int(sys.argv[2])
resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu))
resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
resource.setrlimit(resource.RLIMIT_NPROC, (0, 0))
import socket
def _denied(*a, **k):
    raise PermissionError("network disabled in the evolution sandbox")
socket.socket = socket.create_connection = socket.getaddrinfo = _denied
examples = json.load(sys.stdin)
resource.setrlimit(resource.RLIMIT_NOFILE, (8, 8))
spec = importlib.util.spec_from_file_location("candidate", sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
print(json.dumps([module.score_event(e["features"]) for e in examples]))
"""


def benchmark_from_ledger(ledger) -> list[dict]:
    """[{features, label}] from facts 'scout_event_*' that have a recorded outcome (latest wins)."""
    from ..kernel import facts
    facts._ensure_facts_table(ledger)
    facts._ensure_outcomes_table(ledger)
    rows = ledger.db.execute(
        "SELECT f.id, f.object, (SELECT o.outcome FROM fact_outcomes o WHERE o.fact_id=f.id "
        "ORDER BY o.recorded_at DESC LIMIT 1) FROM facts f WHERE f.subject='owner' "
        "AND f.predicate LIKE 'scout\\_event\\_%' ESCAPE '\\' ORDER BY f.id").fetchall()
    examples = []
    for _, obj, outcome in rows:
        if outcome not in POSITIVE | NEGATIVE:
            continue
        try:
            features = json.loads(obj)
        except ValueError:
            continue
        if isinstance(features, dict):
            examples.append({"features": features, "label": 1 if outcome in POSITIVE else 0})
    return examples


def pairwise_accuracy(scores: list[float], labels: list[int]) -> float:
    """Share of (liked, not-liked) pairs the scores rank the right way round; ties count half."""
    positives = [s for s, y in zip(scores, labels) if y == 1]
    negatives = [s for s, y in zip(scores, labels) if y == 0]
    if not positives or not negatives:
        return 0.5
    wins = sum(1.0 if p > n else 0.5 if p == n else 0.0 for p in positives for n in negatives)
    return wins / (len(positives) * len(negatives))


def _netns_prefix() -> list[str]:
    """['unshare', '-r', '-n'] if this kernel lets an ordinary user create an empty network namespace."""
    global _NETNS
    if _NETNS is None:
        tool = shutil.which("unshare")
        try:
            ok = bool(tool) and subprocess.run([tool, "-r", "-n", "true"], capture_output=True, timeout=5).returncode == 0
        except (OSError, subprocess.SubprocessError):
            ok = False
        _NETNS = [tool, "-r", "-n"] if ok else []
    return _NETNS


_NETNS: list[str] | None = None


def run_candidate(program_path: str, examples: list[dict], cpu_seconds: int = 5) -> list[float]:
    proc = subprocess.run(_netns_prefix() + [sys.executable, "-I", "-S", "-c", RUNNER, program_path, str(min(int(cpu_seconds), 5))],
                          input=json.dumps(examples).encode(), capture_output=True, timeout=20,
                          env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"})
    if proc.returncode != 0:
        raise RuntimeError("candidate failed to run")
    scores = json.loads(proc.stdout)
    if not isinstance(scores, list) or len(scores) != len(examples) or not all(isinstance(s, (int, float)) for s in scores):
        raise RuntimeError("candidate returned malformed scores")
    return [float(s) for s in scores]


def evaluate_source(candidate_source: str, program_path: str, examples: list[dict]) -> dict:
    found = guard.violations(BASELINE.read_text(encoding="utf-8"), candidate_source)
    if found:
        return {"combined_score": -999.0, "safety_violations": len(found), "violations": found, "examples": len(examples)}
    if len(examples) < 8 or len({e["label"] for e in examples}) < 2:
        return {"combined_score": 0.0, "safety_violations": 0, "examples": len(examples), "status": "NOT_ENOUGH_EXAMPLES"}
    try:
        scores = run_candidate(program_path, examples)
    except Exception as exc:
        return {"combined_score": -999.0, "safety_violations": 1, "violations": [f"runtime: {type(exc).__name__}"], "examples": len(examples)}
    return {"combined_score": round(pairwise_accuracy(scores, [e["label"] for e in examples]), 4),
            "safety_violations": 0, "examples": len(examples), "status": "SCORED"}


def select_benchmark(ledger, min_real: int = MIN_LABELLED_OUTCOMES) -> tuple[list[dict], str]:
    """(examples, "REAL") once enough rated picks exist; otherwise (fixtures, "BOOTSTRAP")."""
    from . import bootstrap
    real = benchmark_from_ledger(ledger) if ledger is not None else []
    if len(real) >= max(min_real, MIN_LABELLED_OUTCOMES):
        return real, "REAL"
    return bootstrap.fixtures(), "BOOTSTRAP"


def evaluate(program_path: str) -> dict:
    """OpenEvolve entry point. The benchmark is a JSON file named by APEX_EVOLUTION_BENCHMARK
    (exported from the Ledger by promote_gate.export_benchmark), so the sandbox needs no database;
    with no file it scores against the bootstrap fixtures."""
    from . import bootstrap
    path = os.environ.get(BENCHMARK_ENV, "")
    examples = json.loads(Path(path).read_text(encoding="utf-8")) if path and Path(path).is_file() else bootstrap.fixtures()
    return evaluate_source(Path(program_path).read_text(encoding="utf-8"), program_path, examples)
