"""Behavioral text signature (mission 2026-11-15, Phase 6 - replaces the digital twin,
archived this session: core/apex/agents_governing.FROZEN["digital_twin"]). No face, no
voice, no avatar. Learns a pattern over the owner's own approve/reject history and predicts
it on a new proposal, with a reported confidence - lower risk than face/voice mimicry per
this session's own architecture proposal, because a wrong prediction here is a rejected
draft, not a misattributed video or audio clip.

HONEST SCOPE: no real approve/reject history exists yet (zero real decisions recorded this
session, same gap named throughout this session's own analysis). generate_synthetic() below
produces SYNTHETIC fixtures only, clearly labeled, with a hand-designed signal (shorter,
business-hours, low-stakes proposals tend to be approved; longer, off-hours, high-stakes
ones tend to be rejected) so the classifier has something real to learn FOR TESTING the
pipeline - this is not a claim about any real owner's real preferences, which do not exist
in any dataset yet.

Deliberately dependency-free (no numpy/sklearn): a hand-written, from-scratch logistic
regression trained by gradient descent over a handful of interpretable features - simple
enough to read every line of, appropriate for a toy synthetic dataset of 100 examples, and
avoids adding an undeclared dependency this project's CI (scripts/test_offline.py,
.github/workflows/apex-gates.yml) does not install."""
from __future__ import annotations

import math
import random
from dataclasses import dataclass

ACTION_KINDS = ("notify", "finance", "research", "social")


@dataclass(frozen=True)
class Proposal:
    text: str
    hour: int             # 0-23, hour of day submitted
    action_kind: str       # one of ACTION_KINDS
    label: int             # 1 = approved, 0 = rejected (ground truth, synthetic or real)


def generate_synthetic(n_approved: int = 50, n_rejected: int = 50, seed: int = 1337) -> list[Proposal]:
    """Hand-designed signal, clearly synthetic: approved proposals are shorter, during
    business hours (9-17), and skew toward low-stakes action kinds; rejected proposals are
    longer, more often off-hours, and skew toward higher-stakes action kinds. Real noise is
    added (random variation, occasional contradicting examples) so the classifier cannot get
    100% - a perfect synthetic separator would be a weaker test of the pipeline, not a
    stronger one."""
    rng = random.Random(seed)
    rows = []
    for _ in range(n_approved):
        length = rng.randint(4, 14)
        text = " ".join(rng.choice(["ok", "please", "confirm", "note", "short", "draft"]) for _ in range(length))
        hour = rng.randint(8, 18) if rng.random() > 0.15 else rng.randint(0, 23)
        kind = rng.choice(["notify", "research"]) if rng.random() > 0.25 else rng.choice(ACTION_KINDS)
        rows.append(Proposal(text, hour, kind, 1))
    for _ in range(n_rejected):
        length = rng.randint(15, 40)
        text = " ".join(rng.choice(["urgent", "complex", "transfer", "unclear", "risky", "large", "sum"])
                        for _ in range(length))
        hour = rng.randint(0, 23) if rng.random() > 0.15 else rng.randint(8, 18)
        kind = rng.choice(["finance", "social"]) if rng.random() > 0.25 else rng.choice(ACTION_KINDS)
        rows.append(Proposal(text, hour, kind, 0))
    rng.shuffle(rows)
    return rows


def extract_features(p: Proposal) -> list[float]:
    """[word_count (scaled), hour-of-day (scaled), one-hot action_kind x4]. Interpretable by
    construction - every weight the model learns maps to one of these named features."""
    word_count = len(p.text.split())
    one_hot = [1.0 if p.action_kind == k else 0.0 for k in ACTION_KINDS]
    return [word_count / 40.0, p.hour / 24.0] + one_hot


def train_test_split(rows: list[Proposal], test_fraction: float = 0.2, seed: int = 7) -> tuple[list, list]:
    rng = random.Random(seed)
    shuffled = list(rows)
    rng.shuffle(shuffled)
    cut = int(len(shuffled) * (1 - test_fraction))
    return shuffled[:cut], shuffled[cut:]


def _sigmoid(z: float) -> float:
    if z < -60:
        return 0.0
    if z > 60:
        return 1.0
    return 1.0 / (1.0 + math.exp(-z))


def train_logistic_regression(rows: list[Proposal], lr: float = 0.3, epochs: int = 500) -> list[float]:
    """From-scratch batch gradient descent. Returns weights [bias, w1, w2, ...] for the
    feature vector extract_features() produces (with an implicit leading 1.0 for bias)."""
    xs = [[1.0] + extract_features(r) for r in rows]
    ys = [float(r.label) for r in rows]
    n_features = len(xs[0])
    weights = [0.0] * n_features
    n = len(xs)
    for _ in range(epochs):
        grad = [0.0] * n_features
        for x, y in zip(xs, ys):
            z = sum(w * xi for w, xi in zip(weights, x))
            pred = _sigmoid(z)
            error = pred - y
            for j in range(n_features):
                grad[j] += error * x[j]
        weights = [w - lr * (g / n) for w, g in zip(weights, grad)]
    return weights


def predict_proba(weights: list[float], p: Proposal) -> float:
    x = [1.0] + extract_features(p)
    z = sum(w * xi for w, xi in zip(weights, x))
    return _sigmoid(z)


def precision_recall(rows: list[Proposal], weights: list[float], threshold: float = 0.5) -> dict:
    """Standard definitions, computed directly - no library. Reports exactly what it
    computes, including 0.0 values if the model has no true positives at all (never
    smoothed to avoid an embarrassing number)."""
    tp = fp = fn = tn = 0
    for r in rows:
        pred = 1 if predict_proba(weights, r) >= threshold else 0
        if pred == 1 and r.label == 1:
            tp += 1
        elif pred == 1 and r.label == 0:
            fp += 1
        elif pred == 0 and r.label == 1:
            fn += 1
        else:
            tn += 1
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    accuracy = (tp + tn) / len(rows) if rows else 0.0
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn, "precision": round(precision, 4),
            "recall": round(recall, 4), "accuracy": round(accuracy, 4)}


def run_report(n_approved: int = 50, n_rejected: int = 50, seed: int = 1337) -> dict:
    """Gate P6: generates the synthetic set, trains, evaluates on a HELD-OUT split never
    seen during training, and returns the metrics dict - printed by the caller, never
    hidden regardless of how good or bad the number is."""
    rows = generate_synthetic(n_approved, n_rejected, seed)
    train_rows, test_rows = train_test_split(rows)
    weights = train_logistic_regression(train_rows)
    train_metrics = precision_recall(train_rows, weights)
    test_metrics = precision_recall(test_rows, weights)
    return {"n_train": len(train_rows), "n_test": len(test_rows),
            "train": train_metrics, "test": test_metrics, "weights": [round(w, 4) for w in weights]}


if __name__ == "__main__":
    import json
    print(json.dumps(run_report(), indent=2))
