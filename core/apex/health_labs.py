"""Parse owner-exported laboratory result TEXT into structured, provenance-tagged rows.

RESEARCH AID ONLY. This is not a medical device, gives no diagnosis, no advice and no clinical
interpretation. Raw health data must stay local per the specification: this module is pure,
performs no file, network or database access and stores nothing. The input is text the owner already
extracted from a report with a local tool; no PDF library is used. Units are never guessed: a value, unit
or printed range that cannot be parsed with certainty sets needs_review. LOW/HIGH/NORMAL is computed only
from a fully parsed printed two-sided range and merely restates the comparison.
Nothing here has been tested (TESTS_NOT_RUN); only py_compile was run.
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from .kernel.schema import identifier

MAX_CHARS = 2_000_000
MAX_LINE = 400
MAX_DIGITS = 14

_PAGE = re.compile(r"\s*page\s+(\d{1,4})(?:\s*(?:of|/)\s*\d{1,4})?\s*", re.IGNORECASE)
_NUM = r"\d+(?:\.\d+)?"
_RESULT = re.compile(
    r"(?P<test>[A-Za-z][A-Za-z0-9 ()/%,'.\-]{0,78}?)\s+(?P<cmp>[<>]=?)?\s*(?P<val>" + _NUM + r")(?P<rest>(?:\s.*)?)")
_COMMA_DECIMAL = re.compile(r"\d,\d")
_BR = re.compile(r"[()\[\]]")
_RANGE = re.compile(r"(?P<lo>" + _NUM + r")\s*(?:-|–|—|to)\s*(?P<hi>" + _NUM + r")")
_UPPER = re.compile(r"(?:<|≤|<=)\s*(?P<hi>" + _NUM + r")")
_LOWER = re.compile(r"(?:>|≥|>=)\s*(?P<lo>" + _NUM + r")")
_FLAG = re.compile(r"\s+(?:H|L|HH|LL|HIGH|LOW|\*)\s*$")
_UNIT = re.compile(r"(?=.*[A-Za-z%µμ])[A-Za-z0-9µμ%/^*.·\-]{1,32}")


def _dec(text):
    if text is None or len(text.replace(".", "")) > MAX_DIGITS:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def _parse_rest(rest):
    """Return (unit, ref_low, ref_high, ref_text, printed_flag, certain)."""
    rest = _BR.sub(" ", rest).strip()
    flag = None
    match = _FLAG.search(" " + rest)
    if match:
        flag = match.group().strip()
        rest = (" " + rest)[:match.start()].strip()
    low = high = ref_text = None
    for pattern in (_RANGE, _UPPER, _LOWER):
        found = list(pattern.finditer(rest))
        if len(found) == 1 and rest[found[0].end():].strip() == "":
            m = found[0]
            low = m.groupdict().get("lo")
            high = m.groupdict().get("hi")
            ref_text = m.group().strip()
            rest = rest[:m.start()].strip()
            break
    unit = rest if rest and _UNIT.fullmatch(rest) else None
    certain = unit is not None and ref_text is not None
    if rest and unit is None:
        certain = False
    return unit, low, high, ref_text, flag, certain


def parse_lab_text(text: str, document_id: str, max_lines: int = 5000) -> list[dict]:
    """Return one dict per recognised result line. Unrecognised lines are ignored, never guessed."""
    document_id = identifier(document_id)
    if not isinstance(text, str) or len(text) > MAX_CHARS or "\x00" in text:
        raise ValueError("Invalid lab text")
    if type(max_lines) is not int or not 1 <= max_lines <= 50_000:
        raise ValueError("Invalid max_lines")
    lines = text.splitlines()
    if len(lines) > max_lines:
        raise ValueError("Too many lines")
    page, results = None, []
    for number, raw in enumerate(lines, 1):
        if len(raw) > MAX_LINE:
            continue
        line = " ".join(raw.split())
        if not line:
            continue
        marker = _PAGE.fullmatch(line)
        if marker:
            page = int(marker.group(1))
            continue
        match = _RESULT.fullmatch(line)
        if not match:
            continue
        test, comparator, value, rest = (match["test"].strip(), match["cmp"], match["val"], match["rest"])
        row = {"test": test, "value": None, "value_num": None, "value_comparator": comparator, "unit": None,
               "ref_low": None, "ref_high": None, "ref_text": None, "printed_flag": None, "flag": "UNKNOWN",
               "page": page, "line_no": number, "document_id": document_id, "needs_review": True}
        number_value = _dec(value)
        if _COMMA_DECIMAL.search(rest[:3]) or rest.startswith(",") or number_value is None:
            results.append(row)  # decimal comma or oversize number: keep provenance, no value
            continue
        unit, low, high, ref_text, printed, certain = _parse_rest(rest)
        row.update(value=value, value_num=float(number_value), unit=unit, ref_low=low, ref_high=high,
                   ref_text=ref_text, printed_flag=printed)
        lo, hi = _dec(low), _dec(high)
        if lo is not None and hi is not None and lo <= hi and comparator is None:
            row["flag"] = "LOW" if number_value < lo else "HIGH" if number_value > hi else "NORMAL"
        row["needs_review"] = not (certain and comparator is None and row["flag"] != "UNKNOWN")
        results.append(row)
    return results


def reference_check(result: dict) -> dict:
    """Restate whether the parsed value lies inside the parsed printed two-sided range. No interpretation."""
    if not isinstance(result, dict):
        raise ValueError("Invalid result")
    value, lo, hi = _dec(result.get("value")), _dec(result.get("ref_low")), _dec(result.get("ref_high"))
    if value is None or lo is None or hi is None or lo > hi or result.get("value_comparator") is not None:
        return {"inside_printed_range": None,
                "statement": "Value or printed two-sided range could not be parsed with certainty."}
    inside = lo <= value <= hi
    return {"inside_printed_range": inside,
            "statement": f"Parsed value {result['value']} is {'inside' if inside else 'outside'} the printed range "
                         f"{result['ref_low']} to {result['ref_high']}. This is not a clinical interpretation."}
