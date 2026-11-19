"""Property scout from official open data: HM Land Registry UK House Price Index, per outer-London borough.
Shows which boroughs' AVERAGE sold prices by house type sit within the owner's budget, plus stamp duty and an
illustrative repayment. Averages are not listings: it narrows where to look, it does not find a house. All sums in code."""
from __future__ import annotations

import json

BOROUGHS = ["barking-and-dagenham", "barnet", "bexley", "brent", "bromley", "croydon", "ealing", "enfield", "haringey",
            "harrow", "havering", "hillingdon", "hounslow", "kingston-upon-thames", "merton", "newham", "redbridge",
            "richmond-upon-thames", "sutton", "waltham-forest"]
BASE = "https://landregistry.data.gov.uk/data/ukhpi/region"
# SDLT residential bands for England from 1 April 2025 (GOV.UK). Rates change at Budgets: verify before relying on them.
SDLT_STANDARD = [(125_000, 0), (250_000, 2), (925_000, 5), (1_500_000, 10), (None, 12)]
SDLT_FIRST_TIME = [(300_000, 0), (500_000, 5)]            # relief only when the price is 500,000 or less


def sdlt(price: int, first_time: bool = False) -> int:
    bands = SDLT_FIRST_TIME if first_time and price <= 500_000 else SDLT_STANDARD
    tax, prev = 0.0, 0
    for upto, rate in bands:
        top = price if upto is None else min(price, upto)
        if top > prev:
            tax += (top - prev) * rate / 100
        prev = top if upto is None else upto
        if upto is None or price <= upto:
            break
    return int(tax)


def monthly_payment(loan: float, annual_rate_pct: float, years: int = 25) -> int:
    r, n = annual_rate_pct / 1200, years * 12
    return round(loan * r / (1 - (1 + r) ** -n)) if r else round(loan / n)


def _topic(raw: bytes) -> dict:
    return (json.loads(raw).get("result") or {}).get("primaryTopic") or {}


def run(fetch, budget: int = 450_000, boroughs=None) -> dict:
    failed, rows, month = [], [], None
    try:
        items = (json.loads(fetch(f"{BASE}/barnet.json?_pageSize=1&_sort=-refMonth")).get("result") or {}).get("items") or []
        month = str(items[0]).rsplit("/", 1)[-1]
    except Exception as exc:                                       # noqa: BLE001
        return {"event": "property", "status": "ERROR", "detail": f"latest month lookup failed: {type(exc).__name__}", "rows": []}
    for slug in (boroughs or BOROUGHS):
        try:
            t = _topic(fetch(f"{BASE}/{slug}/month/{month}.json"))
            row = {"borough": slug.replace("-", " ").title(), "terraced": t.get("averagePriceTerraced"), "semi": t.get("averagePriceSemiDetached"),
                   "flat": t.get("averagePriceFlatMaisonette"), "first_time_buyer": t.get("averagePriceFirstTimeBuyer"),
                   "annual_change_pct": t.get("percentageAnnualChange")}
            if isinstance(row["terraced"], (int, float)):
                row["terraced_within_budget"] = row["terraced"] <= budget
                row["gap_to_terraced"] = int(row["terraced"] - budget)
                rows.append(row)
        except Exception as exc:                                   # noqa: BLE001
            failed.append(f"{slug}:{type(exc).__name__}")
    rows.sort(key=lambda r: r["terraced"])
    return {"event": "property", "status": "OK" if rows else "NO_DATA", "month": month, "budget": budget, "feeds_failed": failed,
            "rows": rows, "within_budget": [r["borough"] for r in rows if r["terraced_within_budget"]],
            "costs_at_budget": {"sdlt_standard": sdlt(budget), "sdlt_first_time_buyer": sdlt(budget, True), "deposit_10pct": budget // 10,
                                "monthly_illustration": {f"{p}%": monthly_payment(budget * 0.9, p) for p in (4, 5, 6)},
                                "note": "Repayment is an illustration on a 90% loan over 25 years at assumed rates, not a quote."},
            "source": "HM Land Registry UK House Price Index (Open Government Licence)"}
