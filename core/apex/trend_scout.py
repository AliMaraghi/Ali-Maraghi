"""Public trend scan (Google Trends daily RSS per country) and short-form script drafts from the local model.
Nothing is published: drafts are stored for the owner. A country whose feed fails is recorded as failed, not skipped silently."""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET

GEOS = {"GB": "en", "US": "en", "DE": "de", "FR": "fr", "ES": "es", "TR": "tr", "IR": "fa", "AE": "ar"}
NS = {"ht": "https://trends.google.com/trending/rss"}
MAX_BYTES = 1_500_000


def feed_url(geo: str) -> str:
    return f"https://trends.google.com/trending/rss?geo={geo}"


def _traffic(text: str) -> int:
    m = re.match(r"\s*([\d,.]+)\s*([KkMm]?)\+?", text or "")
    if not m:
        return 0
    n = float(m.group(1).replace(",", ""))
    return int(n * {"k": 1_000, "m": 1_000_000}.get(m.group(2).lower(), 1))


def parse(raw: bytes, geo: str) -> list:
    if not isinstance(raw, bytes) or len(raw) > MAX_BYTES:
        raise ValueError("feed too large")
    out = []
    for item in ET.fromstring(raw).iter("item"):
        title = (item.findtext("title") or "").strip()[:120]
        if not title:
            continue
        news = [(n.findtext("ht:news_item_title", "", NS) or "").strip()[:160] for n in item.findall("ht:news_item", NS)]
        out.append({"term": title, "geo": geo, "lang": GEOS.get(geo, "en"),
                    "traffic": _traffic(item.findtext("ht:approx_traffic", "", NS)), "news": [n for n in news if n][:2]})
    return out


def scan(fetch, geos=None) -> dict:
    trends, failed = [], []
    for geo in (geos or GEOS):
        try:
            trends.extend(parse(fetch(feed_url(geo)), geo))
        except Exception as exc:                                   # noqa: BLE001 - recorded
            failed.append(f"{geo}:{type(exc).__name__}")
    by_term: dict = {}
    for t in trends:                                               # the same term trending in several countries scores higher
        e = by_term.setdefault(t["term"].lower(), {**t, "geos": [], "traffic": 0})
        e["geos"].append(t["geo"])
        e["traffic"] += t["traffic"]
    ranked = sorted(by_term.values(), key=lambda e: -(e["traffic"] * (1 + 0.5 * (len(e["geos"]) - 1))))
    for e in ranked:
        e["score"] = round(e["traffic"] * (1 + 0.5 * (len(e["geos"]) - 1)))
        e.pop("geo", None)
    return {"event": "trends", "status": "OK" if ranked else "NO_DATA", "feeds_failed": failed, "count": len(ranked), "top": ranked[:15]}


SYSTEM = ("You write one short-form video script idea. Reply ONLY with JSON: "
          '{"hook": "first spoken line, under 15 words", "beats": ["3 short beats"], "angle": "explainer|reaction|how_to|story", '
          '"platform": "tiktok|youtube_shorts|youtube_long"}. Write in the language code given. State no facts or numbers '
          "beyond the headline provided. No medical, financial or legal advice.")


def draft(llm, trend: dict, lessons=None) -> dict | None:
    """One script draft for one trend from the local model. None if the model is absent or returns junk."""
    import json
    if llm is None:
        return None
    try:
        system = SYSTEM + ("\nLessons from review (style only): " + "; ".join(lessons) if lessons else "")
        raw = llm(system, f"LANGUAGE: {trend['lang']}\nTREND: {trend['term']}\nHEADLINES: {'; '.join(trend.get('news') or [])}", 300)
        obj = json.loads(raw[raw.find("{"): raw.rfind("}") + 1])
    except Exception:                                              # noqa: BLE001
        return None
    if not isinstance(obj, dict) or not isinstance(obj.get("hook"), str) or not isinstance(obj.get("beats"), list):
        return None
    return {"term": trend["term"], "lang": trend["lang"], "geos": trend.get("geos"), "trend_score": trend.get("score"),
            "hook": obj["hook"][:200], "beats": [str(b)[:200] for b in obj["beats"][:4]],
            "angle": str(obj.get("angle", ""))[:20], "platform": str(obj.get("platform", ""))[:20], "state": "DRAFT_NEEDS_OWNER",
            "agent": "A-11", "prompt_version": __import__("hashlib").sha256(system.encode()).hexdigest()[:12]}
