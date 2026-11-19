"""Economics, behavioural patterns and a money-flow graph, computed ONLY from the stored weekly spending record.

Plain arithmetic on the owner's own figures. Every item carries its evidence and a strength; nothing here
diagnoses a person or claims a cause. Needs enough weeks of data, otherwise it says so instead of guessing.
"""
from __future__ import annotations

from statistics import mean, pstdev

SKIP = {"Card payment / own-account transfer", "Failed card payment (reversed)", "Other / uncategorised"}
ESSENTIAL = {"Housing & council", "Utilities", "Groceries", "Transport", "Health & fitness", "Interest & bank fees", "Insurance"}
CONVENIENCE = {"Food delivery", "Eating out & coffee"}
MIN_WEEKS = 8


def _series(record: dict | None) -> dict:
    cats = {c: s for c, s in ((record or {}).get("weekly_category_pence") or {}).items() if c not in SKIP and s}
    return cats


def _weeks(cats: dict, income: dict) -> list:
    return sorted(set().union(*[set(s) for s in cats.values()], set(income))) if cats else []


def _pearson(a: list, b: list) -> float | None:
    if len(a) < MIN_WEEKS or pstdev(a) == 0 or pstdev(b) == 0:
        return None
    ma, mb = mean(a), mean(b)
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / (len(a) * pstdev(a) * pstdev(b))


def economics(record: dict | None) -> dict | None:
    cats, income = _series(record), (record or {}).get("weekly_in_pence") or {}
    weeks = _weeks(cats, income)
    if len(weeks) < MIN_WEEKS:
        return None
    out = [sum(s.get(w, 0) for s in cats.values()) for w in weeks]
    inc = [income.get(w, 0) for w in weeks]
    totals = {c: sum(s.values()) for c, s in cats.items()}
    spend = sum(totals.values()) or 1
    top3 = sorted(totals.items(), key=lambda kv: -kv[1])[:3]
    recent, before = out[-4:], out[-12:-4]
    return {
        "weeks": len(weeks), "avg_weekly_out_pence": round(mean(out)), "avg_weekly_in_pence": round(mean(inc)),
        "net_weekly_pence": round(mean(inc) - mean(out)),
        "out_volatility_pct": round(100 * pstdev(out) / mean(out)) if mean(out) else 0,
        "income_volatility_pct": round(100 * pstdev(inc) / mean(inc)) if mean(inc) else 0,
        "essential_share_pct": round(100 * sum(v for c, v in totals.items() if c in ESSENTIAL) / spend),
        "convenience_share_pct": round(100 * sum(v for c, v in totals.items() if c in CONVENIENCE) / spend),
        "top3": [{"category": c, "share_pct": round(100 * v / spend)} for c, v in top3],
        "recent_vs_before_pct": round(100 * (mean(recent) - mean(before)) / mean(before)) if before and mean(before) else None,
    }


def behaviour(record: dict | None) -> list:
    """Observed patterns in the numbers. Each: {name, evidence, strength: weak|moderate|strong}. No causes claimed."""
    from . import spending_rules
    found = []
    e = economics(record)
    if not e:
        return found
    pd = spending_rules.payday_effect(record)
    if pd and pd["avg_out_other_pence"]:
        ratio = pd["avg_out_high_income_pence"] / pd["avg_out_other_pence"]
        if ratio >= 1.25:
            found.append({"name": "Spending rises in weeks money arrives",
                          "evidence": f"Average outgoings £{pd['avg_out_high_income_pence']/100:.0f} in the {pd['high_income_weeks']} biggest-income weeks vs £{pd['avg_out_other_pence']/100:.0f} otherwise ({ratio:.1f}x, {pd['weeks']} weeks). Large bills landing on pay weeks also cause this.",
                          "strength": "strong" if ratio >= 2 else "moderate"})
    if e["convenience_share_pct"] >= 25:
        found.append({"name": "Large share goes on convenience food",
                      "evidence": f"Food delivery plus eating out and coffee is {e['convenience_share_pct']}% of tracked spending; groceries and essentials together are {e['essential_share_pct']}%.",
                      "strength": "strong" if e["convenience_share_pct"] >= 40 else "moderate"})
    if e["out_volatility_pct"] >= 60:
        found.append({"name": "Weekly spending is very uneven",
                      "evidence": f"Weekly outgoings swing by about {e['out_volatility_pct']}% around the £{e['avg_weekly_out_pence']/100:.0f} average.",
                      "strength": "moderate"})
    r = e["recent_vs_before_pct"]
    if r is not None and abs(r) >= 25:
        found.append({"name": "Spending is trending " + ("up" if r > 0 else "down"),
                      "evidence": f"Last 4 weeks average {abs(r)}% {'above' if r > 0 else 'below'} the 8 weeks before.",
                      "strength": "moderate"})
    if e["net_weekly_pence"] < 0:
        found.append({"name": "Outgoings exceed recorded income",
                      "evidence": f"Average £{abs(e['net_weekly_pence'])/100:.0f} a week more out than in across {e['weeks']} weeks. Income into accounts you have not uploaded is not counted.",
                      "strength": "moderate"})
    return found


def graph(record: dict | None, min_r: float = 0.6) -> dict | None:
    """Money-flow graph: an 'Income' node, one node per category (weight = total pence), and edges between categories whose
    weekly amounts move together (Pearson r >= min_r over 8+ shared weeks). Correlation only; no cause."""
    cats, income = _series(record), (record or {}).get("weekly_in_pence") or {}
    weeks = _weeks(cats, income)
    if len(weeks) < MIN_WEEKS:
        return None
    nodes = [{"id": "Income", "pence": sum(income.values())}] + [{"id": c, "pence": sum(s.values())} for c, s in cats.items()]
    vec = {c: [s.get(w, 0) for w in weeks] for c, s in cats.items()}
    vec["Income"] = [income.get(w, 0) for w in weeks]
    edges, names = [], list(vec)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            r = _pearson(vec[a], vec[b])
            if r is not None and r >= min_r:
                edges.append({"a": a, "b": b, "r": round(r, 2)})
    edges.sort(key=lambda x: -x["r"])
    return {"weeks": len(weeks), "nodes": sorted(nodes, key=lambda n: -n["pence"]), "edges": edges[:12]}
