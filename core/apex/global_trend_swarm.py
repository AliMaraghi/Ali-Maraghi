"""Global trend scan: Google Trends daily feeds for thirteen markets in nine languages, merged and ranked for a
worldwide audience. One sequential pass in the existing background cycle (no resident agents, a few MB of memory).

What the numbers are: "volume" is the search-volume band Google publishes; "velocity" is the change in that band since
our previous scan, per hour (None on a first sighting); "crossover" counts distinct markets and languages where the
exact same term is trending (the same story spelt differently in two scripts is NOT merged); "fit" is a keyword
heuristic. The final score is a ranking aid, uncalibrated against any real outcome. Viral hooks and audience pain points
cannot be read from these feeds and are not claimed.
"""
from __future__ import annotations

import math
import re

from . import trend_scout

MARKETS = {"US": "en", "GB": "en", "ES": "es", "MX": "es", "BR": "pt", "PT": "pt", "SA": "ar", "EG": "ar", "FR": "fr", "DE": "de",
           "IN": "hi", "JP": "ja", "KR": "ko"}
FIT = {"technology": (1.3, r"\b(ai|iphone|android|app|tesla|nvidia|openai|chatgpt|robot|samsung|google|apple|microsoft)\b"),
       "money": (1.2, r"\b(bitcoin|crypto|stock|inflation|price|salary|bank|tax)\b"),
       "entertainment": (1.1, r"\b(trailer|netflix|album|movie|film|series|season|game|gta|concert)\b"),
       "lifestyle": (1.1, r"\b(recipe|diet|fitness|travel|flight|hotel|fashion|skincare)\b")}
AVOID = re.compile(r"\b(dead|dies|death|killed|shooting|crash|earthquake|war|attack|murder|funeral|obituary)\b", re.I)
FIXTURE = re.compile(r"\b(vs\.?|v)\b|\s[-–]\s", re.I)                # "Team A vs Team B": over in a day, little to say to a world audience


def scan(fetch, previous: dict | None = None, now: float = 0.0, markets=None) -> dict:
    """fetch(url) -> bytes. previous is the last recorded scan, used only to compute velocity."""
    markets = markets or MARKETS
    rows, failed = [], []
    for geo, lang in markets.items():
        try:
            for t in trend_scout.parse(fetch(trend_scout.feed_url(geo)), geo):
                rows.append({**t, "lang": lang})
        except Exception as exc:                                   # noqa: BLE001 - recorded, never silently skipped
            failed.append(f"{geo}:{type(exc).__name__}")
    before = {t["term"].lower(): t.get("volume", 0) for t in (previous or {}).get("all", [])}
    hours = max((now - (previous or {}).get("scanned_at", now)) / 3600, 0)
    merged: dict = {}
    for r in rows:
        e = merged.setdefault(r["term"].lower(), {"term": r["term"], "markets": [], "languages": [], "volume": 0, "news": []})
        e["markets"].append(r["geo"])
        if r["lang"] not in e["languages"]:
            e["languages"].append(r["lang"])
        e["volume"] += r["traffic"]
        e["news"] = (e["news"] + r["news"])[:2]
    out = []
    for key, e in merged.items():
        text = (e["term"] + " " + " ".join(e["news"])).lower()
        fit, tags = 1.0, []
        for tag, (weight, pattern) in FIT.items():
            if re.search(pattern, text):
                fit, tags = max(fit, weight), tags + [tag]
        avoid = bool(AVOID.search(text))
        short_lived = bool(FIXTURE.search(e["term"]))
        velocity = round((e["volume"] - before[key]) / hours) if key in before and hours >= 0.5 else None
        crossover = 1 + 0.6 * (len(e["languages"]) - 1) + 0.2 * (len(e["markets"]) - len(e["languages"]))
        score = math.log10(e["volume"] + 10) * crossover * fit * (0.2 if avoid else 1) * (0.5 if short_lived else 1)
        out.append({**e, "velocity_per_hour": velocity, "fit_tags": tags, "sensitive": avoid, "short_lived": short_lived,
                    "english_first": "en" in e["languages"] or len(e["languages"]) > 1, "score": round(score, 2)})
    out.sort(key=lambda e: -e["score"])
    return {"event": "global_trends", "status": "OK" if out else "NO_DATA", "scanned_at": now, "markets_ok": len(markets) - len(failed), "markets": len(markets),
            "feeds_failed": failed, "count": len(out), "cross_language": sum(1 for e in out if len(e["languages"]) > 1),
            "top": out[:12], "all": [{"term": e["term"], "volume": e["volume"]} for e in out[:400]],
            "note": "Score is a ranking heuristic, not a measured prediction. Hooks and pain points are not read from these feeds."}
