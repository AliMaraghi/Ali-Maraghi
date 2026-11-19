"""Priority maths for the OS runner: Bayesian approval posterior, expected utility with time discount and
opportunity cost, and a UCB1 exploration bonus. Pure arithmetic on recorded counts; no model, no invented inputs."""
from __future__ import annotations

import math


def posterior(approved: int, declined: int, prior_a: float = 1.0, prior_b: float = 1.0) -> float:
    """Beta-Bernoulli mean: probability the owner accepts this kind of item, from his own past approve/decline record."""
    return (approved + prior_a) / (approved + declined + prior_a + prior_b)


def discount(hours_until_useful: float, half_life_hours: float = 48.0) -> float:
    """Exponential time discount: value halves every half_life_hours of delay. 1.0 for now or overdue."""
    return 0.5 ** (max(0.0, hours_until_useful) / half_life_hours)


def expected_utility(value: float, p_accept: float, hours_until_useful: float, cost: float, best_alternative: float = 0.0) -> float:
    """value*P(accept)*discount - cost - opportunity cost (the best alternative use of the same slot)."""
    return value * p_accept * discount(hours_until_useful) - cost - best_alternative


def ucb(mean_reward: float, pulls: int, total_pulls: int, c: float = 1.4) -> float:
    """UCB1: favour arms that paid off, but keep trying rarely-run ones. Never-run arms come first."""
    if pulls <= 0:
        return float("inf")
    return mean_reward + c * math.sqrt(math.log(max(total_pulls, 1)) / pulls)


def surprise(age_seconds: float | None, expected_seconds: float) -> float:
    """Prediction error for a source expected to refresh every expected_seconds: 0 when fresh, grows with staleness,
    capped at 10. A source never seen is maximally surprising."""
    if age_seconds is None:
        return 10.0
    return round(min(10.0, max(0.0, age_seconds / expected_seconds - 1.0)), 2)
