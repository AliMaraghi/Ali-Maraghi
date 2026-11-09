"""Bounded offline tools: scenario arithmetic, consent-aware planning and media intake.

No account, model, renderer, or network is called. Inputs remain untrusted data.
These tools cannot establish demand, consent, legal rights or real-world outcomes.
"""
from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from itertools import islice
from pathlib import Path
import stat
from typing import Iterable

Number = Decimal | int | float | str
_WORKSPACE = Path(__file__).resolve().parents[2]


def _number(value: Number, label: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (Decimal, int, float, str)):
        raise ValueError(f"{label} must be a finite number")
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f"{label} must be a finite number") from exc
    if not result.is_finite() or result < 0 or result > Decimal("1e12"):
        raise ValueError(f"{label} must be finite and between zero and 1e12")
    return result


def _text(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 4000:
        raise ValueError(f"{label} must contain 1 to 4000 characters")
    return value


def _integer(value: int, label: str, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"{label} must be an integer between {minimum} and {maximum}")
    return value


@dataclass(frozen=True)
class Interval:
    """Nonnegative assumption interval, not a confidence interval."""
    low: Number
    high: Number

    def __post_init__(self) -> None:
        low, high = _number(self.low, "low"), _number(self.high, "high")
        if low > high:
            raise ValueError("Interval low cannot exceed high")
        object.__setattr__(self, "low", low)
        object.__setattr__(self, "high", high)

    def json(self) -> dict[str, str]:
        return {"low": str(self.low), "high": str(self.high)}


@dataclass(frozen=True)
class OpportunityScenario:
    opportunity_id: str
    title: str
    success_probability: Interval
    revenue_if_success_gbp: Interval
    cash_cost_gbp: Interval
    hours_required: Interval
    hourly_time_value_gbp: Interval
    assumptions: tuple[str, ...]
    smallest_experiment: str
    time_to_first_action_minutes: int
    evidence_refs: tuple[str, ...] = ()


def evaluate_opportunity(scenario: OpportunityScenario) -> dict:
    """Endpoint bounds: probability * conditional gross revenue - cash - time.

    Cash and time costs occur in both success and failure. This bounds the
    supplied assumption box; it does not estimate actual likelihood or income.
    """
    for field in ("opportunity_id", "title", "smallest_experiment"):
        _text(getattr(scenario, field), field)
    ranges = (scenario.success_probability, scenario.revenue_if_success_gbp,
              scenario.cash_cost_gbp, scenario.hours_required, scenario.hourly_time_value_gbp)
    if not all(isinstance(item, Interval) for item in ranges):
        raise ValueError("Scenario amounts must be Interval objects")
    if scenario.success_probability.high > 1:
        raise ValueError("Success probability cannot exceed one")
    if not isinstance(scenario.assumptions, tuple) or not scenario.assumptions:
        raise ValueError("Explicit assumptions are required")
    for assumption in scenario.assumptions:
        _text(assumption, "assumption")
    if not isinstance(scenario.evidence_refs, tuple):
        raise ValueError("Evidence references must be a tuple")
    for reference in scenario.evidence_refs:
        _text(reference, "evidence reference")
    _integer(scenario.time_to_first_action_minutes, "time to first action", 1, 525600)
    p, revenue, cash, hours, hourly = ranges
    low = p.low * revenue.low - cash.high - hours.high * hourly.high
    high = p.high * revenue.high - cash.low - hours.low * hourly.low
    return {
        "schema_version": "apex.opportunity.v1", "opportunity_id": scenario.opportunity_id,
        "title": scenario.title, "status": "ASSUMPTION_SCENARIO_NOT_VERIFIED_OPPORTUNITY",
        "currency": "GBP", "expected_net_value_gbp": {"low": str(low), "high": str(high)},
        "cash_at_risk_gbp": str(cash.high),
        "worst_case_including_time_gbp": str(-cash.high - hours.high * hourly.high),
        "inputs": {"success_probability": p.json(), "revenue_if_success_gbp": revenue.json(),
                   "cash_cost_gbp": cash.json(), "hours_required": hours.json(),
                   "hourly_time_value_gbp": hourly.json()},
        "formula": "success_probability * revenue_if_success - cash_cost - hours * hourly_time_value",
        "assumptions": list(scenario.assumptions), "evidence_refs": list(scenario.evidence_refs),
        "smallest_experiment": scenario.smallest_experiment,
        "time_to_first_action_minutes": scenario.time_to_first_action_minutes,
        "critic": ["Probability and revenue assumptions need independent demand evidence.",
                   "Eligibility, taxes, competition and legal constraints remain unassessed.",
                   "Time has an opportunity cost even when additional API spending is zero."],
        "verified_demand": False, "realized_income_gbp": None, "external_actions": [],
        "actual_external_spend_gbp": "0",
    }


@dataclass(frozen=True)
class PersonalTask:
    task_id: str
    title: str
    minutes: int
    priority: int
    energy: str = "low"
    kind: str = "solo"
    consent: str = "not_applicable"


def plan_day(tasks: Iterable[PersonalTask], available_minutes: int, *, low_energy: bool = False) -> dict:
    """Greedy priority schedule. Low energy is a preference, not a diagnosis."""
    _integer(available_minutes, "available minutes", 0, 1440)
    if type(low_energy) is not bool:
        raise ValueError("low_energy must be a boolean")
    items = list(islice(tasks, 1001))
    if len(items) > 1000:
        raise ValueError("At most 1000 tasks are allowed")
    ids = set()
    for task in items:
        if not isinstance(task, PersonalTask):
            raise ValueError("Tasks must be PersonalTask objects")
        _text(task.task_id, "task id")
        _text(task.title, "title")
        if task.task_id in ids:
            raise ValueError("Duplicate task id")
        ids.add(task.task_id)
        _integer(task.minutes, "minutes", 1, 1440)
        _integer(task.priority, "priority", 0, 5)
        if task.energy not in {"low", "medium", "high"} or task.kind not in {"solo", "contact"}:
            raise ValueError("Unknown energy or task kind")
        if task.consent not in {"not_applicable", "granted", "unknown", "withdrawn"}:
            raise ValueError("Unknown consent state")
    selected, deferred = [], []
    used = 0
    for task in sorted(items, key=lambda t: (-t.priority, t.minutes, t.task_id)):
        reason = None
        if task.kind == "contact" and task.consent != "granted":
            reason = "CONTACT_CONSENT_ABSENT_OR_WITHDRAWN"
        elif low_energy and task.energy != "low":
            reason = "LOW_ENERGY_PREFERENCE"
        elif used + task.minutes > available_minutes:
            reason = "TIME_BUDGET"
        if reason:
            deferred.append({"task_id": task.task_id, "reason": reason})
            continue
        selected.append({"task_id": task.task_id, "title": task.title,
                         "start_minute": used, "end_minute": used + task.minutes,
                         "mode": "DRAFT_FOR_REVIEW" if task.kind == "contact" else "SUGGESTED"})
        used += task.minutes
    return {"schema_version": "apex.personal.v1", "schedule": selected, "deferred": deferred,
            "minutes_used": used, "minutes_remaining": available_minutes - used,
            "method": "priority_descending_then_duration_ascending_then_id",
            "external_actions": [], "contact_authorized": False,
            "outcome_status": "PLAN_ONLY_NOT_MEASURED_PRODUCTIVITY"}


@dataclass(frozen=True)
class MediaAsset:
    asset_id: str
    relative_path: str
    kind: str = "video"
    rights_status: str = "unverified"
    rights_reference: str = ""
    owner_approved: bool = False


@dataclass(frozen=True)
class Shot:
    shot_id: str
    duration_seconds: int
    asset_id: str
    visual: str
    narration: str
    sound: str
    framing: str = "16:9"


def build_production_manifest(shots: Iterable[Shot], assets: Iterable[MediaAsset], *,
                              workspace: Path = _WORKSPACE) -> dict:
    """Inspect operator-authorized local metadata; never decode, render or publish.

    Rights are attestations, not independent legal verification. Existence is
    not media validity. No bytes of source assets are read.
    """
    root = Path(workspace).resolve(strict=True)
    if not root.is_relative_to(_WORKSPACE) or not root.is_dir():
        raise ValueError("Asset workspace must be inside the development workspace")
    items, media = list(islice(shots, 101)), list(islice(assets, 301))
    if not 1 <= len(items) <= 100 or len(media) > 300:
        raise ValueError("Expected 1 to 100 shots and at most 300 assets")
    asset_map = {}
    for asset in media:
        if not isinstance(asset, MediaAsset):
            raise ValueError("Assets must be MediaAsset objects")
        _text(asset.asset_id, "asset id")
        if asset.asset_id in asset_map:
            raise ValueError("Duplicate asset id")
        if asset.kind not in {"video", "audio", "image"}:
            raise ValueError("Unknown media kind")
        if asset.rights_status not in {"unverified", "owner_attested", "licensed"}:
            raise ValueError("Unknown rights status")
        if type(asset.owner_approved) is not bool:
            raise ValueError("owner_approved must be a boolean")
        if not isinstance(asset.rights_reference, str) or len(asset.rights_reference) > 4000:
            raise ValueError("Invalid rights reference")
        _text(asset.relative_path, "relative path")
        asset_map[asset.asset_id] = asset
    timeline, blockers, asset_checks, ids = [], [], [], set()
    elapsed = 0
    for shot in items:
        if not isinstance(shot, Shot):
            raise ValueError("Shots must be Shot objects")
        for field in ("shot_id", "asset_id", "visual", "sound"):
            _text(getattr(shot, field), field)
        if not isinstance(shot.narration, str) or len(shot.narration) > 4000:
            raise ValueError("Invalid narration")
        if shot.shot_id in ids:
            raise ValueError("Duplicate shot id")
        ids.add(shot.shot_id)
        _integer(shot.duration_seconds, "shot duration", 1, 90)
        if shot.framing not in {"16:9", "9:16"}:
            raise ValueError("Unsupported aspect ratio")
        timeline.append({"shot_id": shot.shot_id, "start_seconds": elapsed,
                         "end_seconds": elapsed + shot.duration_seconds,
                         "asset_id": shot.asset_id, "visual": shot.visual,
                         "narration": shot.narration, "sound": shot.sound,
                         "framing": shot.framing})
        elapsed += shot.duration_seconds
        if shot.asset_id not in asset_map:
            blockers.append({"asset_id": shot.asset_id, "reason": "MISSING_ASSET_RECORD"})
    if not 60 <= elapsed <= 90:
        raise ValueError("Film timeline must total 60 to 90 seconds")
    for asset in media:
        reason = None
        relative = Path(asset.relative_path)
        path = root / relative
        if relative.is_absolute() or ".." in relative.parts:
            reason = "PATH_OUTSIDE_WORKSPACE"
        elif asset.rights_status == "unverified" or not asset.rights_reference.strip() or not asset.owner_approved:
            reason = "RIGHTS_OR_OWNER_APPROVAL_MISSING"
        else:
            try:
                current = root
                for part in relative.parts:
                    current /= part
                    if current.is_symlink():
                        raise ValueError("Symlink asset path")
                if not path.resolve().is_relative_to(root):
                    reason = "PATH_OUTSIDE_WORKSPACE"
                elif not stat.S_ISREG(path.stat().st_mode) or path.stat().st_size == 0:
                    reason = "NOT_NONEMPTY_REGULAR_FILE"
            except (OSError, ValueError):
                reason = "MISSING_OR_UNSAFE_ASSET_FILE"
        asset_checks.append({"asset_id": asset.asset_id, "status": reason or "LOCAL_INTAKE_CHECK_ONLY",
                             "rights_basis": asset.rights_status, "media_decoded": False})
        if reason:
            blockers.append({"asset_id": asset.asset_id, "reason": reason})
    return {"schema_version": "apex.video.v1", "title": "Invisible Systems: The Art of Being Somewhere Else",
            "location": "Lagos, Portugal", "duration_seconds": elapsed,
            "status": "BLOCKED" if blockers else "READY_FOR_EDITOR_REVIEW",
            "timeline": timeline, "asset_checks": asset_checks, "blockers": blockers,
            "export_plan": {"primary_aspect_ratio": "16:9", "secondary_aspect_ratio": "9:16",
                            "primary_resolution": "1920x1080", "audio_sample_rate_hz": 48000,
                            "subtitle_format": "SRT", "fps": "MATCH_APPROVED_SOURCE_AFTER_INSPECTION"},
            "quality_review_required": ["Decode media and verify trim durations", "Review composition and continuity",
                                        "Check speech intelligibility, peaks and loudness", "Verify subtitle timing",
                                        "Verify rights including ambient music and identifiable people",
                                        "Founder style approval and independent viewer feedback"],
            "rendered_video_path": None, "film_completed": False, "external_actions": [],
            "actual_external_spend_gbp": "0", "founder_style_approved": False}
