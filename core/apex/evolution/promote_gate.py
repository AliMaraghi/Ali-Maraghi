"""Human-in-the-loop promotion gate for evolved candidates. Nothing here merges anything.

A candidate that (a) passes the static guard and the sandbox with zero violations and (b)
beats the current baseline by >= 5% becomes a PENDING proposal in the existing ApprovalBook,
carrying the unified diff, the benchmark delta and the benchmark mode (REAL rated history, or
BOOTSTRAP simulated fixtures). A person approves or declines it in the console. The Telegram
notice carries a link to that proposal only - the existing telegram_bot rule (notice with a
link, never the content), which this module follows rather than loosens. Approving records
the decision; applying the diff to the repository is still a reviewed commit by a person.

Every generation, promoted or not, is written to the `evolution_log` table in the existing
SQLite database. Mutation calls to a model are capped at EVOLUTION_MONTHLY_CAP_PENCE on top
of the global monthly hard cap in kernel/budget.py.
"""
from __future__ import annotations

import difflib
import json
import tempfile
import time
from pathlib import Path

from ..kernel.budget import BudgetDenied, window_start
from . import config, evaluator

MIN_IMPROVEMENT = 0.05
EVOLUTION_MONTHLY_CAP_PENCE = 500
PROVIDER, POOL, SKU = "anthropic", "intelligence", "evolution-step"
PROPOSER = "agent:evolution-lab"


class EvolutionBudgetExceeded(BudgetDenied):
    pass


def _ensure_log(db) -> None:
    db.execute("""
        CREATE TABLE IF NOT EXISTS evolution_log (
          id INTEGER PRIMARY KEY, recorded_at REAL NOT NULL, generation TEXT NOT NULL,
          baseline_score REAL, candidate_score REAL, examples INTEGER NOT NULL,
          safety_violations INTEGER NOT NULL, decision TEXT NOT NULL, detail TEXT NOT NULL)
    """)


def reserve_mutation(budget, key: str) -> None:
    """Budget gate for one model call that proposes a mutation: sub-cap first, then the normal
    reservation (which also enforces the pool caps and the global monthly hard cap)."""
    spent = budget.ledger.db.execute(
        "SELECT COALESCE(SUM(CASE WHEN state='SETTLED' THEN MAX(actual_minor,0) WHEN state='RESERVED' "
        "THEN reserved_minor ELSE 0 END),0) FROM budget_reservations WHERE sku=? AND created_at>=?",
        (SKU, window_start("month", budget.clock()))).fetchone()[0]
    price = budget.price(PROVIDER, SKU, budget.clock())
    cap = min(EVOLUTION_MONTHLY_CAP_PENCE, int(config.load()["monthly_cap_pence"]))
    if spent + -(-price // 1000) > cap:
        raise EvolutionBudgetExceeded(f"EVOLUTION_SUB_CAP:{spent}>{EVOLUTION_MONTHLY_CAP_PENCE}")
    budget.reserve(key, POOL, PROVIDER, SKU, 1)


def export_benchmark(ledger, path: Path) -> int:
    examples = evaluator.benchmark_from_ledger(ledger)
    Path(path).write_text(json.dumps(examples), encoding="utf-8")
    return len(examples)


def consider(ledger, book, candidate_source: str, generation: str, examples: list[dict] | None = None,
             notify=None, now: float | None = None, mode: str | None = None) -> dict:
    """Score baseline and candidate on the same examples and, if the gate is met, raise a
    proposal. Returns the decision record that was logged. `notify(proposal_id)` is optional."""
    now = time.time() if now is None else now
    baseline_source = evaluator.BASELINE.read_text(encoding="utf-8")
    settings = config.load()
    if examples is None:
        examples, mode = evaluator.select_benchmark(ledger, int(settings["min_real_outcomes"]))
    mode = mode or "SUPPLIED"
    threshold = max(MIN_IMPROVEMENT, float(settings["min_improvement"]))
    with tempfile.TemporaryDirectory() as tmp:
        candidate_path = Path(tmp) / "candidate.py"
        candidate_path.write_text(candidate_source, encoding="utf-8")
        base = evaluator.evaluate_source(baseline_source, str(evaluator.BASELINE), examples)
        cand = evaluator.evaluate_source(candidate_source, str(candidate_path), examples)
    record = {"generation": generation, "mode": mode, "examples": len(examples), "baseline_score": base.get("combined_score"),
              "candidate_score": cand.get("combined_score"), "safety_violations": cand.get("safety_violations", 0)}
    if cand.get("safety_violations"):
        record.update(decision="REJECTED_UNSAFE", detail="; ".join(cand.get("violations", []))[:500])
    elif cand.get("status") != "SCORED" or base.get("status") != "SCORED":
        record.update(decision="NOT_ENOUGH_EXAMPLES", baseline_score=None, candidate_score=None,
                      detail=f"{len(examples)} examples; at least 8 with both outcomes needed")
    else:
        b, c = float(base["combined_score"]), float(cand["combined_score"])
        gain = (c - b) / b if b > 0 else 0.0
        if candidate_source == baseline_source or gain < threshold:
            record.update(decision="NO_IMPROVEMENT", detail=f"gain {gain:+.1%}; {threshold:.0%} needed")
        else:
            diff = "".join(difflib.unified_diff(baseline_source.splitlines(True), candidate_source.splitlines(True),
                                                "target_heuristics.py (current)", "target_heuristics.py (candidate)"))
            proposal_id = f"evo.{int(now)}"
            state = book.propose(proposal_id, "opportunity", "evolution-promote", PROPOSER,
                                 {"diff": diff[:8000], "baseline_score": b, "candidate_score": c,
                                  "gain": round(gain, 4), "examples": len(examples), "benchmark_mode": mode},
                                 [f"evolution:{generation}"],
                                 commentary=(f"Evolved ranking weights: {b:.3f} -> {c:.3f} on {len(examples)} "
                                             + ("of your own rated picks." if mode == "REAL" else
                                                "SIMULATED fixture tasks (bootstrap mode - not real results yet).")))
            record.update(decision=f"PROPOSED_{state}", detail=proposal_id)
            if notify is not None and state == "PENDING":
                try:
                    notify(proposal_id)
                except Exception:
                    pass                      # a failed notice never changes the decision
    _ensure_log(ledger.db)
    ledger.db.execute("INSERT INTO evolution_log (recorded_at, generation, baseline_score, candidate_score, examples, "
                      "safety_violations, decision, detail) VALUES (?,?,?,?,?,?,?,?)",
                      (now, f"{generation[:60]}|{mode}", record["baseline_score"], record["candidate_score"], record["examples"],
                       record["safety_violations"], record["decision"], record["detail"]))
    return record


def run_generation(ledger, book, seed: int, notify=None, now: float | None = None) -> dict:
    """One scheduled run: try N seeded mutations, log each, and raise at most ONE proposal (the
    best). Does nothing unless ENABLE_EVOLUTION_SANDBOX is on. Costs nothing: no model is called."""
    import random
    from . import mutate
    if not config.enabled():
        return {"status": "DISABLED", "flag": config.FLAG}
    if ledger.db.execute("SELECT 1 FROM sqlite_master WHERE name='proposals'").fetchone() and ledger.db.execute(
            "SELECT 1 FROM proposals WHERE kind='evolution-promote' AND state='PENDING'").fetchone():
        return {"status": "WAITING_FOR_OWNER", "detail": "an earlier evolution proposal is still pending"}
    now = time.time() if now is None else now
    settings = config.load()
    examples, mode = evaluator.select_benchmark(ledger, int(settings["min_real_outcomes"]))
    baseline_source = evaluator.BASELINE.read_text(encoding="utf-8")
    rng = random.Random(seed)
    base = evaluator.evaluate_source(baseline_source, str(evaluator.BASELINE), examples)
    best_source, best_score, tried = None, float(base.get("combined_score", 0.0)), 0
    with tempfile.TemporaryDirectory() as tmp:
        for index in range(int(settings["candidates_per_run"])):
            source = mutate.mutate(baseline_source, rng)
            path = Path(tmp) / f"c{index}.py"
            path.write_text(source, encoding="utf-8")
            score = evaluator.evaluate_source(source, str(path), examples).get("combined_score", -999.0)
            tried += 1
            if score > best_score:
                best_source, best_score = source, score
    if best_source is None:
        _ensure_log(ledger.db)
        ledger.db.execute("INSERT INTO evolution_log (recorded_at, generation, baseline_score, candidate_score, examples, "
                          "safety_violations, decision, detail) VALUES (?,?,?,?,?,0,'NO_IMPROVEMENT',?)",
                          (now, f"seed{seed}|{mode}", base.get("combined_score"), best_score, len(examples), f"{tried} candidates tried"))
        return {"status": "NO_IMPROVEMENT", "mode": mode, "tried": tried, "baseline_score": base.get("combined_score")}
    record = consider(ledger, book, best_source, f"seed{seed}", examples, notify, now, mode)
    return {"status": record["decision"], "mode": mode, "tried": tried, **{k: record[k] for k in ("baseline_score", "candidate_score", "detail")}}
