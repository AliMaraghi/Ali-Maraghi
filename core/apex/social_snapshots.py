"""Daily social metric snapshot schema and validation. Status: TESTS_NOT_RUN.

No platform API is called here. Adapters (not yet written) hand rows to `validate_row`; manual CSV rows
use the same schema so a platform without app access still has a supported fallback.
Platform capability notes below come from the owner-supplied API_HINTS and are NOT verified against
official documentation in this repository yet.
"""
from __future__ import annotations

import re

PLATFORMS = ("instagram", "threads", "linkedin", "x", "youtube", "tiktok", "snapchat")
SOURCES = ("api", "manual_csv")
METRICS = ("followers", "views", "likes", "comments", "shares", "posts")

CAPABILITY_NOTES = {
    "instagram": "Insights/publishing need a Business or Creator account linked to a Facebook Page (owner-supplied, unverified).",
    "threads": "Dedicated Threads API (owner-supplied, unverified).",
    "linkedin": "Member posting scope differs from company/partner products (owner-supplied, unverified).",
    "x": "Pay-per-use access since Feb 2026 (owner-supplied, unverified).",
    "youtube": "Testing-mode OAuth apps have short-lived refresh tokens (owner-supplied, unverified).",
    "tiktok": "Approved posting API and audit required (owner-supplied, unverified).",
    "snapchat": "Public Profile API product required (owner-supplied, unverified).",
}


def validate_row(row: dict) -> dict:
    """Return a normalised snapshot row or raise ValueError. Counts are non-negative integers."""
    if not isinstance(row, dict):
        raise ValueError("Row must be an object")
    platform, date, source = row.get("platform"), row.get("date"), row.get("source")
    if platform not in PLATFORMS or source not in SOURCES:
        raise ValueError("Unknown platform or source")
    if not isinstance(date, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
        raise ValueError("date must be YYYY-MM-DD")
    metrics = row.get("metrics")
    if not isinstance(metrics, dict) or not metrics or set(metrics) - set(METRICS):
        raise ValueError("metrics must be a non-empty object of known metric names")
    for name, value in metrics.items():
        if type(value) is not int or not 0 <= value <= 10**12:
            raise ValueError(f"{name} must be a non-negative integer")
    account = row.get("account_label", "")
    if not isinstance(account, str) or len(account) > 80:
        raise ValueError("account_label too long")
    return {"platform": platform, "date": date, "source": source, "account_label": account, "metrics": dict(metrics)}


def daily_delta(previous: dict, current: dict) -> dict:
    """Per-metric change between two validated snapshots of the same platform and account."""
    if (previous["platform"], previous["account_label"]) != (current["platform"], current["account_label"]):
        raise ValueError("Snapshots must be for the same platform and account")
    if current["date"] <= previous["date"]:
        raise ValueError("current must be later than previous")
    return {m: current["metrics"][m] - previous["metrics"][m] for m in current["metrics"] if m in previous["metrics"]}
