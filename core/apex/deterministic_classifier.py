"""Rule-based spending categories: fixed keywords, no model, the same answer every time.

The rules in this file are general UK ones (national chains, standard bank wording), most
specific first. Rules that are personal to the owner - local shops, an employer's name, his own
name on transfers - are NOT in the code: they live in runtime/inbox/classifier_rules.json on his
server (never committed) and are applied before these. Anything no rule matches is
"Other / uncategorised" - never guessed. Only totals leave this module: `summarise` returns sums
per category, a weekly series for food ordered in or eaten out, and a balance reconciliation
when the file prints balances. Individual transactions are not returned and are never stored.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

OTHER = "Other / uncategorised"
FOOD = ("Food delivery", "Eating out & coffee")
PRIVATE_RULES = ("runtime", "inbox", "classifier_rules.json")
# (category, keywords). First match wins, matched on the upper-cased description.
RULES = (
    ("Benefits: Universal Credit", ("DWP UC",)),
    ("Benefits: Carer's Allowance", ("DWP CA",)),
    ("Benefits: PIP", ("DWP PIP",)),
    ("Salary", ("SALARY", "WAGES", "PAYROLL")),
    ("Failed card payment (reversed)", ("UNPAID DIRECT",)),
    ("Interest & bank fees", ("INTEREST", "CLUB LLOYDS", "NON-STERLING", "NON STERLING", "MONEY ADVANCE", "OVERDRAFT FEE", "LATE FEE")),
    ("Food delivery", ("JUST EAT", "JUST-EAT", "DELIVEROO", "UBER EATS", "UBEREATS", "DOMINO")),
    ("Eating out & coffee", ("PRET A", "CAFFE NERO", "COSTA", "STARBUCKS", "MCDONALD", "WATCHHOUSE", "GAILS", "GAIL'S", "LOUNGE",
                             "TIM HORTONS", "NANDO", "GREGGS", "KFC", "BURGER KING", "RESTAURANT", "CAFE", "COFFEE")),
    ("Groceries", ("TESCO", "SAINSBURY", "LIDL", "ALDI", "CO-OP", "CO OP", "WAITROSE", "MARKS&SPENCER", "M&S SIMPLY", "ASDA", "MORRISONS",
                   "NISA", "ICELAND", "SUPERMARKET", "SUPERSTORE")),
    ("Transport", ("TFL", "UBER", "UBR", "RINGGO", "PARKING", "HORIZONPARK", "BP ", "SHELL", "ESSO", "RONTEC", "TRAINLINE", "BOLT", "ADDISON LEE")),
    ("Housing & council", ("LONDON BOROUGH", "LB OF", "COUNCIL TAX", "RENT")),
    ("Utilities & telecoms", ("EDF", "COMMUNITYFIBRE", "O2", "THAMES WATER", "BRITISH GAS", "OCTOPUS", "EE LIMITED", "VODAFONE", "THREE", "BT GROUP", "DOM & GEN")),
    ("Subscriptions & software", ("OPENAI", "CHATGPT", "APPLE.COM", "APPLE COM", "AMAZON PRIME", "NETFLIX", "SPOTIFY", "GOOGLE", "PAYPAL PAYMENT", "ANTHROPIC")),
    ("Health & fitness", ("PUREGYM", "PURE GYM", "THE GYM", "BARBER", "PHARMACY", "HOLLAND &", "DENTAL")),
    ("Shopping", ("AMAZON", "AMZ", "BOOTS", "VERY ", "KLARNA", "IHERB", "EBAY", "ARGOS", "IKEA", "ZARA", "H&M")),
    ("Cash", ("ATM", "NOTEMACHINE", "CASH WITHDRAWAL", "CASHPOINT")),
    ("Card payment / own-account transfer", ("PAYMENT RECEIVED", "FASTER PAYMENT", "CREDIT CARD", "AMERICAN EXP", "HALIFAX CLARITY",
                                             "LLOYDS BANK", "NW MASTERCARD", "DIRECT DEBIT PAYMENT", "PAYMENT - THANK YOU")),
)
CATEGORIES = tuple(name for name, _ in RULES) + (OTHER,)
SPENDING = tuple(c for c in CATEGORIES if not c.startswith(("Benefits", "Salary", "Card payment", "Failed card")))


def check_rules(value) -> tuple:
    """Validates owner rules: [[category, [keyword, ...]], ...] with known categories only."""
    if not isinstance(value, list) or len(value) > 60:
        raise ValueError("rules must be a short list")
    out = []
    for entry in value:
        if not (isinstance(entry, list) and len(entry) == 2 and entry[0] in CATEGORIES and entry[0] != OTHER
                and isinstance(entry[1], list) and 1 <= len(entry[1]) <= 80):
            raise ValueError("each rule is [category, [keywords]]")
        words = tuple(" ".join(str(k).upper().replace("*", " ").replace("/", " ").split()) for k in entry[1])
        if not all(isinstance(k, str) for k in entry[1]) or not all(2 <= len(w) <= 40 for w in words):
            raise ValueError("keywords are 2-40 characters")
        out.append((entry[0], words))
    return tuple(out)


def load_private_rules(root) -> tuple:
    path = Path(root).joinpath(*PRIVATE_RULES)
    try:
        if not path.is_file() or path.stat().st_size > 50_000:
            return ()
        return check_rules(json.loads(path.read_text(encoding="utf-8")).get("rules"))
    except (OSError, ValueError, AttributeError):
        return ()


def classify(description: str, extra: tuple = ()) -> str:
    text = " " + " ".join(str(description or "").upper().replace("*", " ").replace("/", " ").split()) + " "
    for category, keywords in tuple(extra) + RULES:
        if any(k in text for k in keywords):
            return category
    return OTHER


def card_signs_flipped(transactions: list, extra: tuple = ()) -> bool:
    """Card exports (Amex and others) print spending as positive. True when most rows that are
    plainly shop spending carry a plus sign, so the caller can turn the whole file round."""
    signs = [t["pence"] > 0 for t in transactions if t["pence"] and classify(t["description"], extra) in SPENDING
             and classify(t["description"], extra) != OTHER]
    return len(signs) >= 5 and sum(signs) / len(signs) >= 0.7


def week_start(day: date) -> date:
    return day - timedelta(days=day.weekday())            # Monday


def summarise(transactions: list, extra: tuple = ()) -> dict:
    """transactions: [{"description", "pence", optional "date" (datetime.date), optional "balance_pence"}]."""
    flipped = card_signs_flipped(transactions, extra)
    totals = {c: {"in_pence": 0, "out_pence": 0, "count": 0} for c in CATEGORIES}
    weekly_food: dict = {}
    weekly_cat: dict = {}
    weekly_in: dict = {}
    days, uncategorised = [], 0
    for t in transactions:
        pence = -t["pence"] if flipped else t["pence"]
        category = classify(t["description"], extra)
        uncategorised += category == OTHER
        bucket = totals[category]
        bucket["count"] += 1
        bucket["in_pence" if pence > 0 else "out_pence"] += abs(pence)
        if isinstance(t.get("date"), date):
            days.append(t["date"])
            key = week_start(t["date"]).isoformat()
            if category in FOOD and pence < 0:
                weekly_food[key] = weekly_food.get(key, 0) - pence
            if pence < 0:
                bucket_w = weekly_cat.setdefault(category, {})
                bucket_w[key] = bucket_w.get(key, 0) - pence
            elif pence > 0 and not category.startswith("Card payment"):
                weekly_in[key] = weekly_in.get(key, 0) + pence
    out = {"totals": {c: v for c, v in totals.items() if v["count"]}, "transaction_count": len(transactions),
           "uncategorized_count": uncategorised, "signs_flipped": flipped,
           "first_date": min(days).isoformat() if days else None, "last_date": max(days).isoformat() if days else None,
           "weekly_food_pence": dict(sorted(weekly_food.items())),
           "weekly_category_pence": {c: dict(sorted(w.items())) for c, w in weekly_cat.items()},
           "weekly_in_pence": dict(sorted(weekly_in.items())), "reconciliation": reconcile(transactions, flipped)}
    return out


def reconcile(transactions: list, flipped: bool = False) -> dict:
    """Checks the file against its own printed balances: first balance + everything after it
    must equal the last balance. Works in whichever order the bank lists rows."""
    rows = [t for t in transactions if isinstance(t.get("balance_pence"), int)]
    if len(rows) < 2 or len(rows) != len(transactions):
        return {"status": "NO_BALANCES"}
    sign = -1 if flipped else 1
    forward = rows[0]["balance_pence"] + sum(sign * t["pence"] for t in rows[1:]) == rows[-1]["balance_pence"]
    backward = rows[-1]["balance_pence"] + sum(sign * t["pence"] for t in rows[:-1]) == rows[0]["balance_pence"]
    return {"status": "OK" if (forward or backward) else "MISMATCH", "rows": len(rows)}
