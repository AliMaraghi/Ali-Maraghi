"""Local importer for a manually exported WhatsApp text chat. Pure functions: no file writes, no network. Status: TESTS_NOT_RUN.

WhatsApp has no personal-account API; the owner exports a chat by hand (Help Center: ZIP with a text file, media excluded). The Help Center
does not publish the line layout, so ONLY the two OBSERVED layouts below are parsed. This module makes NO claim of official-format compliance
and NEVER reports a complete import while anything is unresolved: every unparsed, unsupported, ambiguous, invalid or unclassified item is kept
with its raw text and listed under `unresolved`.

SUPPORTED (observed, not official), 24-hour clock only:
  A  "[dd/mm/yyyy, hh:mm:ss] Name: text"   brackets; '/' or '.' separators; 2- or 4-digit year; comma after the date optional; seconds optional
  B  "dd/mm/yyyy, hh:mm - Name: text"       dash form; same date/time rules; seconds optional
NOT SUPPORTED (reported as `unsupported_layout` with the raw line): AM/PM times, non-ASCII digits, year-first or '-'-separated dates, any other
locale/OS layout. A message line may start with an invisible direction mark, which is stripped.
Lines continuing a multi-line message are appended to it. System lines (no "Name: " part) are kept raw and marked `unclassified`: there is no
verified list of WhatsApp system messages, and a system line that happens to contain ": " is indistinguishable from a message.
Date order is configurable (day-first default). `ambiguous_date` is reported when both numbers are <= 12 and differ; `invalid_date` when the
configured order is impossible. The parsed `sent_at` is a naive local-time string as written in the export (no timezone is known).
"""
from __future__ import annotations

import hashlib
import re

from .agent_contract import wrap_untrusted

MAX_BYTES = 5_000_000
MAX_LINES = 100_000
MAX_TEXT = 4096
MAX_RAW_LINE = 1000
SOURCE = "whatsapp-export"
SUPPORTED_LAYOUTS = {
    "A": "[dd/mm/yyyy, hh:mm:ss] Name: text (24-hour; observed, not official)",
    "B": "dd/mm/yyyy, hh:mm - Name: text (24-hour; observed, not official)",
}
_INVISIBLE = "‎‏‪‫‬﻿"
_STAMP = r"(\d{1,2})[/.](\d{1,2})[/.](\d{2,4}),? (\d{1,2}):(\d{2})(?::(\d{2}))?"
SHAPE_A = re.compile(r"^\[" + _STAMP + r"\] (.*)$")
SHAPE_B = re.compile(r"^" + _STAMP + r" - (.*)$")
SENDER = re.compile(r"^([^:]{1,80}): (.*)$", re.S)
# A line that LOOKS like it starts a timestamped entry but matched neither supported shape.
LOOKS_LIKE_ENTRY = re.compile(r"^\[?\s*\d{1,4}[/.\-]\d{1,2}[/.\-]\d{1,4}")


def _stamp(m, order):
    a, b, y, hh, mm, ss = m.groups()[:6]          # group 7 is the rest of the line
    a, b = int(a), int(b)
    day, month = (a, b) if order == "dmy" else (b, a)
    year = int(y) + (2000 if len(y) == 2 else 0)
    if not (1 <= month <= 12 and 1 <= day <= 31 and int(hh) < 24 and int(mm) < 60 and int(ss or 0) < 60):
        return None, "invalid_date"
    flag = "ambiguous_date" if a <= 12 and b <= 12 and a != b else None
    return f"{year:04d}-{month:02d}-{day:02d} {int(hh):02d}:{mm}:{int(ss or 0):02d}", flag


def _raw(line):
    return line[:MAX_RAW_LINE]


def parse_chat(text, file_name, date_order="dmy"):
    """Return the parse result. `text` is the decoded export; `file_name` is only hashed.

    Keys: records, system_lines, issues, unresolved, counts, import_status, supported_layouts, official_format_compliance (always False),
    provenance. `import_status` is 'UNRESOLVED_ITEMS' when anything is unresolved, else 'NO_UNRESOLVED_ITEMS_DETECTED' (never 'complete').
    """
    if date_order not in ("dmy", "mdy"):
        raise ValueError("date_order must be 'dmy' or 'mdy'")
    if not isinstance(text, str) or not isinstance(file_name, str):
        raise ValueError("text and file_name must be strings")
    if len(text.encode("utf-8", "replace")) > MAX_BYTES:
        raise ValueError("export too large")
    lines = text.splitlines()
    if len(lines) > MAX_LINES:
        raise ValueError("too many lines")
    provenance = {"file_name_sha256": hashlib.sha256(file_name.encode()).hexdigest(), "date_order": date_order}
    records, system, issues, unresolved = [], [], [], []
    current = None

    def flag(no, kind, raw):
        issues.append({"line_no": no, "issue": kind})
        unresolved.append({"line_no": no, "kind": kind, "raw": wrap_untrusted("chat", _raw(raw))})

    def close():
        nonlocal current
        if current is not None:
            body = current["text"].strip()[:MAX_TEXT]
            records.append({"sent_at": current["sent_at"], "sender": current["sender"], "text": wrap_untrusted("chat", body),
                            "raw": wrap_untrusted("chat", "\n".join(_raw(x) for x in current["raw_lines"])),
                            "line_no": current["line_no"], "date_ambiguous": current["ambiguous"], "source": SOURCE,
                            "provenance": {**provenance, "line_no": current["line_no"]}})
            current = None

    for no, raw in enumerate(lines, 1):
        line = raw.lstrip(_INVISIBLE).rstrip(_INVISIBLE)
        m = SHAPE_A.match(line) or SHAPE_B.match(line)
        if not m:
            if LOOKS_LIKE_ENTRY.match(line):
                close()
                flag(no, "unsupported_layout", raw)
            elif current is not None:
                current["text"] += "\n" + line
                current["raw_lines"].append(raw)
            elif line.strip():
                flag(no, "unparsed_line", raw)
            continue
        close()
        sent_at, date_flag = _stamp(m, date_order)
        if sent_at is None:
            flag(no, "invalid_date", raw)
            continue
        if date_flag:
            flag(no, date_flag, raw)
        rest = m.group(7)
        s = SENDER.match(rest)
        if not s:
            system.append({"sent_at": sent_at, "line_no": no, "classification": "unclassified",
                           "text": wrap_untrusted("chat", rest[:MAX_TEXT]), "raw": wrap_untrusted("chat", _raw(raw)),
                           "provenance": {**provenance, "line_no": no}})
            unresolved.append({"line_no": no, "kind": "system_message_unclassified", "raw": wrap_untrusted("chat", _raw(raw))})
            continue
        current = {"sent_at": sent_at, "sender": s.group(1).strip(), "text": s.group(2), "line_no": no,
                   "raw_lines": [raw], "ambiguous": date_flag == "ambiguous_date"}
    close()
    counts = {"records": len(records), "system_lines": len(system), "unresolved": len(unresolved)}
    for item in unresolved:
        counts[item["kind"]] = counts.get(item["kind"], 0) + 1
    return {"records": records, "system_lines": system, "issues": issues, "unresolved": unresolved, "counts": counts,
            "import_status": "UNRESOLVED_ITEMS" if unresolved else "NO_UNRESOLVED_ITEMS_DETECTED",
            "supported_layouts": SUPPORTED_LAYOUTS, "official_format_compliance": False, "provenance": provenance}
