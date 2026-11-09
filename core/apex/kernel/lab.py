"""Reproducible labelled fixture evaluator, not real-world intelligence proof."""
from dataclasses import dataclass, asdict
from time import perf_counter
from typing import Callable
import hashlib
import math
import re

from .engine import canonical
from .schema import identifier


@dataclass(frozen=True)
class Trial:
    id: str
    payload: dict
    expected: bool
    safety_critical: bool = True


@dataclass(frozen=True)
class Receipt:
    candidate: str
    baseline: str
    dataset_sha256: str
    count: int
    candidate_correct: int
    baseline_correct: int
    safety_regressions: int
    repeatable: bool
    eligible: bool
    candidate_seconds: float
    baseline_seconds: float
    scope: str = "SYNTHETIC_FIXTURE_CHECKS_NOT_REAL_WORLD_VALIDATION"

    def to_dict(self):
        return asdict(self)

    def validate(self):
        identifier(self.candidate); identifier(self.baseline)
        counts = (self.count, self.candidate_correct, self.baseline_correct, self.safety_regressions)
        if any(type(x) is not int for x in counts) or not 1 <= self.count <= 1000:
            raise ValueError("Invalid evaluation metrics")
        if any(not 0 <= x <= self.count for x in counts[1:]):
            raise ValueError("Invalid evaluation counts")
        if type(self.repeatable) is not bool or type(self.eligible) is not bool:
            raise ValueError("Invalid evaluation flags")
        if any(type(x) not in (int, float) or not math.isfinite(x) or x < 0 for x in (self.candidate_seconds, self.baseline_seconds)):
            raise ValueError("Invalid evaluation durations")
        if not re.fullmatch(r"[0-9a-f]{64}", self.dataset_sha256) or self.scope != "SYNTHETIC_FIXTURE_CHECKS_NOT_REAL_WORLD_VALIDATION":
            raise ValueError("Invalid evaluation provenance")
        calculated = self.candidate_correct > self.baseline_correct and self.safety_regressions == 0 and self.repeatable and self.count >= 4
        if self.eligible != calculated:
            raise ValueError("Eligibility inconsistent with measured results")


def compare(candidate_name: str, candidate: Callable, baseline_name: str, baseline: Callable,
            trials: tuple[Trial, ...], training_ids: frozenset[str] = frozenset(),
            training_payload_hashes: frozenset[str] = frozenset()) -> Receipt:
    identifier(candidate_name); identifier(baseline_name)
    if not trials or len(trials) > 1000:
        raise ValueError("Bounded nonempty evaluation set required")
    ids = [identifier(t.id) for t in trials]
    payloads = [hashlib.sha256(canonical(t.payload).encode()).hexdigest() for t in trials]
    if len(set(ids)) != len(ids) or len(set(payloads)) != len(payloads):
        raise ValueError("Duplicate evaluation case")
    if set(ids) & training_ids or set(payloads) & training_payload_hashes:
        raise ValueError("Training/holdout leakage")
    if any(type(t.expected) is not bool or type(t.safety_critical) is not bool for t in trials):
        raise ValueError("Boolean ground truth required")
    dataset = hashlib.sha256(canonical([asdict(t) for t in trials]).encode()).hexdigest()
    def run(fn):
        from copy import deepcopy
        values = []
        start = perf_counter()
        for trial in trials:
            try:
                value = fn(deepcopy(trial.payload))
                if type(value) is not bool:
                    value = None
            except Exception:
                value = None
            values.append(value)
        return values, perf_counter() - start
    c, ct = run(candidate); again, _ = run(candidate)
    b, bt = run(baseline); b_again, _ = run(baseline)
    cs = sum(x is t.expected for x, t in zip(c, trials))
    bs = sum(x is t.expected for x, t in zip(b, trials))
    regressions = sum(t.safety_critical and cv is not t.expected for cv, t in zip(c, trials))
    repeatable = c == again and b == b_again and None not in c and None not in b
    eligible = cs > bs and regressions == 0 and repeatable and len(trials) >= 4
    return Receipt(candidate_name, baseline_name, dataset, len(trials), cs, bs, regressions,
                   repeatable, eligible, ct, bt)
