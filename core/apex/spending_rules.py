"""The owner's spending guardrail: one weekly limit on food ordered in or eaten out.

Works only from the totals `deterministic_classifier.summarise` produced for uploaded
statements (kept per source file; no transaction is stored). The alert always names the week
it is about and says when the data is old, so an old statement can never look like "now".
This is the owner's own rule and a display - it blocks nothing and moves no money.
"""
from __future__ import annotations

import time
from datetime import date, timedelta

DEFAULT_WEEKLY_CAP_PENCE = 10_000        # the owner's stated target: 100 pounds a week
STALE_DAYS = 14
MAX_SOURCES = 40


def merge(previous: dict | None, source: str, summary: dict, now: float) -> dict:
    """Adds or replaces one source file's totals and returns the combined record to store."""
    sources = dict((previous or {}).get("sources") or {})
    sources[str(source)[:80] or "statement"] = {k: summary[k] for k in ("totals", "transaction_count", "uncategorized_count", "first_date",
                                                                         "last_date", "weekly_food_pence", "reconciliation", "signs_flipped")}
    sources[str(source)[:80] or "statement"]["weekly_category_pence"] = summary.get("weekly_category_pence") or {}
    sources[str(source)[:80] or "statement"]["weekly_in_pence"] = summary.get("weekly_in_pence") or {}
    for name in sorted(sources, key=lambda n: sources[n].get("last_date") or "")[:-MAX_SOURCES]:
        del sources[name]
    totals, weekly, wcat, win = {}, {}, {}, {}
    for item in sources.values():
        for category, value in item["totals"].items():
            bucket = totals.setdefault(category, {"in_pence": 0, "out_pence": 0, "count": 0})
            for key in bucket:
                bucket[key] += value[key]
        for week, pence in item["weekly_food_pence"].items():
            weekly[week] = weekly.get(week, 0) + pence
        for category, series in (item.get("weekly_category_pence") or {}).items():
            for week, pence in series.items():
                target = wcat.setdefault(category, {})
                target[week] = target.get(week, 0) + pence
        for week, pence in (item.get("weekly_in_pence") or {}).items():
            win[week] = win.get(week, 0) + pence
    dates = [d for item in sources.values() for d in (item.get("first_date"), item.get("last_date")) if d]
    return {"event": "spend_summary", "sources": sources, "totals": totals, "weekly_food_pence": dict(sorted(weekly.items())[-26:]),
            "weekly_category_pence": {c: dict(sorted(w.items())[-26:]) for c, w in wcat.items()},
            "weekly_in_pence": dict(sorted(win.items())[-26:]),
            "first_date": min(dates) if dates else None, "last_date": max(dates) if dates else None,
            "transaction_count": sum(i["transaction_count"] for i in sources.values())}


def food_alert(record: dict | None, cap_pence: int = DEFAULT_WEEKLY_CAP_PENCE, now: float | None = None) -> dict | None:
    """The latest week that has data, against the cap. None when there is nothing dated."""
    weekly = (record or {}).get("weekly_food_pence") or {}
    last = (record or {}).get("last_date")
    if not weekly or not last:
        return None
    now = time.time() if now is None else now
    week = max(weekly)
    through = date.fromisoformat(last)
    age = (date.fromtimestamp(now) - through).days
    recent = [weekly[w] for w in sorted(weekly)[-4:]]
    return {"week_start": week, "week_end": (date.fromisoformat(week) + timedelta(days=6)).isoformat(),
            "current_pence": weekly[week], "cap_pence": cap_pence, "exceeded": weekly[week] > cap_pence,
            "four_week_average_pence": round(sum(recent) / len(recent)), "data_through": last, "stale": age > STALE_DAYS,
            "days_old": age}


def digest(record: dict | None) -> str:
    """One plain line for the daily briefing fallback."""
    totals = (record or {}).get("totals") or {}
    spend = {c: v["out_pence"] for c, v in totals.items() if v["out_pence"] and not c.startswith(("Card payment", "Failed card"))}
    if not spend:
        return ""
    top = max(spend, key=spend.get)
    return (f"Spending in uploaded statements ({record.get('first_date')} to {record.get('last_date')}): "
            f"{sum(spend.values()) / 100:.2f} pounds out; highest category {top} at {spend[top] / 100:.2f} pounds")


SPIKE_RATIO = 1.3


def food_spike(record: dict | None) -> dict | None:
    """The latest week with data, when it is more than 30% above the average of the four weeks
    before it. Returns the plain facts and a neutral question; no cause is suggested."""
    weekly = (record or {}).get("weekly_food_pence") or {}
    weeks = sorted(weekly)
    if len(weeks) < 5:
        return None
    week, before = weeks[-1], [weekly[w] for w in weeks[-5:-1]]
    average = sum(before) / len(before)
    if average <= 0 or weekly[week] <= average * SPIKE_RATIO:
        return None
    return {"week_start": week, "current_pence": weekly[week], "average_pence": round(average),
            "percent_above": round(100 * (weekly[week] / average - 1)),
            "question": (f"Food ordered in or eaten out came to {weekly[week] / 100:.2f} pounds in the week of {week}, "
                         f"against {average / 100:.2f} a week over the four weeks before. Anything about that week worth noting?")}


MIN_EXTRA_PENCE = 2_000                    # ignore a "spike" smaller than 20 pounds over the average


def category_spikes(record: dict | None) -> list:
    """Every spending category whose latest dated week is more than 30% above the average of the four
    weeks before it (and at least 20 pounds above). Plain arithmetic on the stored weekly totals."""
    out = []
    for category, series in ((record or {}).get("weekly_category_pence") or {}).items():
        weeks = sorted(series)
        if len(weeks) < 5:
            continue
        week, before = weeks[-1], [series[w] for w in weeks[-5:-1]]
        average = sum(before) / len(before)
        extra = series[week] - average
        if average > 0 and series[week] > average * SPIKE_RATIO and extra >= MIN_EXTRA_PENCE:
            out.append({"category": category, "week_start": week, "current_pence": series[week], "average_pence": round(average),
                        "percent_above": round(100 * (series[week] / average - 1)), "extra_pence": round(extra)})
    return sorted(out, key=lambda s: -s["extra_pence"])


def top_spike(record: dict | None) -> dict | None:
    """The one thing to ask about: the largest category spike, with a neutral question (no cause suggested)."""
    spikes = category_spikes(record)
    if not spikes:
        return food_spike(record)
    s = spikes[0]
    s["question"] = (f"{s['category']} came to {s['current_pence'] / 100:.2f} pounds in the week of {s['week_start']}, against "
                     f"{s['average_pence'] / 100:.2f} a week over the four weeks before. Anything about that week worth noting?")
    return s


def payday_effect(record: dict | None) -> dict | None:
    """Do weeks with money coming in carry more spending? Compares average weekly outgoings in the
    top-third income weeks with the rest. Needs 9+ weeks; reports counts and averages, no cause."""
    weekly_in = (record or {}).get("weekly_in_pence") or {}
    out_by_week = {}
    for series in ((record or {}).get("weekly_category_pence") or {}).values():
        for week, pence in series.items():
            out_by_week[week] = out_by_week.get(week, 0) + pence
    weeks = sorted(set(weekly_in) & set(out_by_week))
    if len(weeks) < 9:
        return None
    ranked = sorted(weeks, key=lambda w: -weekly_in[w])
    top, rest = ranked[: len(weeks) // 3], ranked[len(weeks) // 3:]
    avg = lambda ws: round(sum(out_by_week[w] for w in ws) / len(ws))  # noqa: E731
    return {"weeks": len(weeks), "high_income_weeks": len(top), "avg_out_high_income_pence": avg(top), "avg_out_other_pence": avg(rest)}
