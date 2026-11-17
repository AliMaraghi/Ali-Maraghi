"""The ONLY code an evolutionary run may change: the block between the two markers.

Layout follows OpenEvolve's convention (EVOLVE-BLOCK-START / EVOLVE-BLOCK-END in the initial
program) so that engine can drive this file later. Everything outside the markers - the
function signatures, the clamping, this docstring - must stay byte-for-byte identical, and
guard.py enforces that along with a syntax allowlist for the block itself.

In scope: ranking weights for scout events, content-angle selection, and model-routing
thresholds. Out of scope, always: budgets, approvals, privacy tiers, the kill switch.
"""
from __future__ import annotations


# EVOLVE-BLOCK-START
EVENT_KEYWORD_WEIGHTS = {
    "singles": 2.0, "mixer": 1.5, "speed dating": 1.5, "networking": 1.5, "tech": 1.0,
    "social": 1.0, "founders": 0.5, "online": -1.0, "webinar": -1.5,
}
CONTENT_ANGLE_WEIGHTS = {"personal_story": 1.0, "analysis": 1.0, "contrarian": 0.5, "how_to": 0.8}
ROUTING = {"long_prompt_chars": 6000, "needs_strong_model_score": 0.7}
WEEKEND_BONUS = 0.5
# EVOLVE-BLOCK-END


def score_event(features: dict) -> float:
    """features: {"text": lowercase title+location, "is_weekend_or_friday_evening": bool}."""
    text = str(features.get("text", ""))
    total = sum(weight for keyword, weight in EVENT_KEYWORD_WEIGHTS.items() if keyword in text)
    if features.get("is_weekend_or_friday_evening"):
        total += WEEKEND_BONUS
    return max(-10.0, min(10.0, float(total)))


def score_angle(angle: str) -> float:
    return max(0.0, min(5.0, float(CONTENT_ANGLE_WEIGHTS.get(angle, 0.0))))
