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
        news_text = " ".join(e["news"]).lower()
        for tag, (weight, pattern) in FIT.items():                 # a tag needs support from a headline, not just a word inside the term
            if re.search(pattern, news_text) or len(set(re.findall(pattern, text))) >= 2:      # ("Gerwyn Price" alone is not "money")
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
            "top": out[:12], "_rows": rows, "all": [{"term": e["term"], "volume": e["volume"]} for e in out[:400]],
            "note": "Score is a ranking heuristic, not a measured prediction. Hooks and pain points are not read from these feeds."}


def persist(db_path, result: dict, raw_rows: list, now: float) -> dict:
    """Write one run into the studio tables: sources, the run, every observation with its original title, topics and
    de-duplicated headlines. Velocity is recomputed from stored history and stays UNKNOWN without a comparable earlier
    observation. One short transaction; called after all network work is finished."""
    import hashlib
    import sqlite3
    run_id = "gts-" + __import__("time").strftime("%Y%m%d-%H%M%S", __import__("time").gmtime(now))
    tid = lambda term: hashlib.sha256(term.lower().encode()).hexdigest()[:16]
    db = sqlite3.connect(str(db_path), timeout=15)
    try:
        with db:
            for geo, lang in MARKETS.items():
                err = next((f.split(":", 1)[1] for f in result["feeds_failed"] if f.startswith(geo + ":")), None)
                db.execute("INSERT INTO studio_global_sources VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(source_id) DO UPDATE SET last_ok=COALESCE(excluded.last_ok,last_ok), "
                           "last_error=excluded.last_error, failures=CASE WHEN excluded.last_error IS NULL THEN 0 ELSE failures+1 END",
                           ("gtrends-" + geo, "google-trends-daily", geo, lang, trend_scout.feed_url(geo), None if err else now, err, 1 if err else 0))
            db.execute("INSERT OR REPLACE INTO studio_global_research_runs VALUES (?,?,?,?,?,?,?)",
                       (run_id, result["scanned_at"], now, result["markets_ok"], len(result["feeds_failed"]), len(raw_rows), ";".join(result["feeds_failed"]) or None))
            unknown = 0
            for r in raw_rows:
                t = tid(r["term"])
                prev = db.execute("SELECT metric_value, observed_at FROM studio_global_trend_observations WHERE topic_id=? AND market=? AND metric_name='approx_traffic' "
                                  "ORDER BY observed_at DESC LIMIT 1", (t, r["geo"])).fetchone()
                db.execute("INSERT OR IGNORE INTO studio_global_trend_observations (run_id, source_id, topic_id, original_title, language, market, source_url, source_family, "
                           "observed_at, published_at, metric_name, metric_value, measurement_window) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                           (run_id, "gtrends-" + r["geo"], t, r["term"], r["lang"], r["geo"], trend_scout.feed_url(r["geo"]), "google-trends-daily", now, None,
                            "approx_traffic", r["traffic"], "daily trending searches (band published by Google)"))
                velocity = "UNKNOWN"
                if prev and now - prev[1] >= 1800:
                    velocity = f"{(r['traffic'] - prev[0]) / ((now - prev[1]) / 3600):+.0f}/h in {r['geo']}"
                else:
                    unknown += 1
                db.execute("INSERT INTO studio_global_topics VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(topic_id) DO UPDATE SET last_seen=excluded.last_seen, velocity=excluded.velocity",
                           (t, r["term"], now, now, None, None, None, None, velocity))
                for h in r["news"]:                                # the same headline seen in several markets is stored once
                    db.execute("INSERT OR IGNORE INTO studio_global_topic_evidence VALUES (?,?,?,?,?)", (t, hashlib.sha256(h.lower().encode()).hexdigest()[:16], h, r["geo"], now))
            for e in result["top"]:
                db.execute("UPDATE studio_global_topics SET markets=?, languages=?, score=?, score_version=? WHERE topic_id=?",
                           (",".join(e["markets"]), ",".join(e["languages"]), e["score"], "gts-score-v2 (heuristic, uncalibrated)", tid(e["term"])))
            counts = {t: db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in ("studio_global_sources", "studio_global_research_runs",
                                                                                          "studio_global_trend_observations", "studio_global_topics", "studio_global_topic_evidence")}
    finally:
        db.close()
    return {"run_id": run_id, "velocity_unknown": unknown, "rows": counts}
