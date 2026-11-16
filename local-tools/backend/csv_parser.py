"""Local bank-statement CSV categorizer: your own export, parsed in-memory, discarded after one
request - nothing is stored, no OAuth, no aggregator, no TrueLayer/Plaid key needed.

Arithmetic (parsing amounts, summing totals per category) is pure Python and never trusted to
the LLM - the one genuinely subjective step is mapping a free-text description to one of a
FIXED category list, which is the only thing the LLM is asked to do, and its answer is
validated against that fixed list before being trusted at all.
"""
from __future__ import annotations

import csv
import io
import re

from anthropic_client import call

CATEGORIES = ("Groceries", "Transport", "Bills", "Dining", "Shopping", "Entertainment", "Income", "Other")
MAX_ROWS = 500
MAX_CSV_CHARS = 200_000
MAX_UNIQUE_DESCRIPTIONS = 100


class CsvParseError(ValueError):
    pass


def _to_pence(raw: str) -> int:
    cleaned = raw.strip().replace(",", "").replace("£", "").replace("$", "")
    negative = False
    if cleaned.startswith("(") and cleaned.endswith(")"):
        cleaned, negative = cleaned[1:-1], True
    try:
        value = float(cleaned)
    except ValueError:
        raise CsvParseError(f"Unparseable amount: {raw!r}") from None
    pence = round(value * 100)
    return -abs(pence) if negative else pence


def _sniff_delimiter(sample: str) -> str:
    """Real banks export comma, semicolon or tab CSVs inconsistently (a UK "Midata" export
    uses ';' with a trailing empty column, for example). Falls back to a count heuristic if
    csv.Sniffer can't decide - never silently misparses every row with no error."""
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t").delimiter
    except csv.Error:
        header = sample.splitlines()[0] if sample.splitlines() else ""
        counts = {d: header.count(d) for d in (",", ";", "\t")}
        best = max(counts, key=counts.get)
        return best if counts[best] > 0 else ","


def _normalize_header(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", name.strip().lower())


def parse_transactions(csv_text: str) -> list:
    """Returns [{"description": str, "pence": int}, ...] - real parsed rows only, nothing
    inferred. Supports a single signed "amount" column (including a combined "Debit/Credit"
    column some UK banks use), or a separate debit/credit pair."""
    if not isinstance(csv_text, str) or not csv_text.strip():
        raise CsvParseError("Empty CSV")
    if len(csv_text) > MAX_CSV_CHARS:
        raise CsvParseError("CSV too large")
    delimiter = _sniff_delimiter(csv_text[:4096])
    reader = csv.DictReader(io.StringIO(csv_text), delimiter=delimiter)
    if not reader.fieldnames:
        raise CsvParseError("No header row found")
    fields = {_normalize_header(f): f for f in reader.fieldnames if f and f.strip()}

    def find(*names):
        for name in names:
            key = _normalize_header(name)
            if key in fields:
                return fields[key]
        return None

    desc_col = find("description", "narrative", "details", "merchant", "payee", "merchant/description")
    amount_col = find("amount", "value", "debit/credit", "debitcredit")
    debit_col = find("debit", "paid out", "paid_out")
    credit_col = find("credit", "paid in", "paid_in")
    if desc_col is None:
        raise CsvParseError("No description/narrative/details/merchant column found")
    if amount_col is None and (debit_col is None or credit_col is None):
        raise CsvParseError("No amount column, and no debit+credit column pair found")

    transactions = []
    for row in reader:
        if len(transactions) >= MAX_ROWS:
            raise CsvParseError(f"Too many rows (max {MAX_ROWS})")
        description = (row.get(desc_col) or "").strip()[:300]
        if not description:
            continue
        if amount_col is not None:
            raw_amount = row.get(amount_col)
            if raw_amount is None or not raw_amount.strip():
                continue
            pence = _to_pence(raw_amount)
        else:
            debit = (row.get(debit_col) or "").strip()
            credit = (row.get(credit_col) or "").strip()
            if debit:
                pence = -abs(_to_pence(debit))
            elif credit:
                pence = abs(_to_pence(credit))
            else:
                continue
        transactions.append({"description": description, "pence": pence})
    if not transactions:
        raise CsvParseError("No usable transaction rows found")
    return transactions


_MAPPING_LINE = re.compile(r"^\s*(\d+)\s*[:.\-]\s*(.+?)\s*$")


def categorize(transactions: list) -> dict:
    """One LLM call classifies each UNIQUE description; Python sums real pence per category.
    Any description the model skips, or maps outside CATEGORIES, falls back to "Other" - never
    a crash, never an invented category."""
    unique = []
    seen = set()
    for t in transactions:
        if t["description"] not in seen:
            seen.add(t["description"])
            unique.append(t["description"])
        if len(unique) >= MAX_UNIQUE_DESCRIPTIONS:
            break
    listing = "\n".join(f"{i + 1}. {d}" for i, d in enumerate(unique))
    system = ("Classify each numbered bank transaction description into EXACTLY one of these "
              "categories: " + ", ".join(CATEGORIES) + ". Reply with exactly one line per "
              "number, format 'N: Category', using only these category names - nothing else, "
              "no explanation.")
    reply = call(system, listing, max_tokens=max(60, len(unique) * 8))

    mapping = {}
    for line in reply.splitlines():
        m = _MAPPING_LINE.match(line)
        if not m:
            continue
        idx = int(m.group(1)) - 1
        category = m.group(2).strip()
        if 0 <= idx < len(unique) and category in CATEGORIES:
            mapping[unique[idx]] = category

    totals_pence = {c: 0 for c in CATEGORIES}
    uncategorized_count = 0
    for t in transactions:
        category = mapping.get(t["description"])
        if category is None:
            category, uncategorized_count = "Other", uncategorized_count + 1
        totals_pence[category] += t["pence"]

    return {"totals_pence": totals_pence, "transaction_count": len(transactions),
            "uncategorized_count": uncategorized_count}
