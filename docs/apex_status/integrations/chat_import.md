# WhatsApp export importer (TESTS_NOT_RUN)
Module: core/apex/chat_import.py. Compiles only. Pure functions; no file I/O, no network.

Source: manual export (https://faq.whatsapp.com/1180414079177245 describes a ZIP with a text file, media excluded; it does not state the extension or show line layout, and no personal-account API exists). Line shapes below are NOT officially documented; they are from commonly seen exports:
- A `[dd/mm/yyyy, hh:mm:ss] Name: text`
- B `dd/mm/yyyy, hh:mm - Name: text`
Handled: multi-line continuation, system lines (no `Name:`), leading/trailing invisible marks (LRM etc.), 2- or 4-digit year, `.` or `/` separators, size/line caps (5 MB, 100000 lines, text 4096), configurable date order (dmy default, mdy), issues `ambiguous_date`, `invalid_date`, `unparsed_line`.
NOT handled: 12-hour AM/PM times, non-Latin digits, locale-specific separators or bracket variants, `Name:` containing a colon, media placeholders and attachment lines (kept as text/system), RTL layouts, iOS vs Android differences beyond the shapes above, a system line that happens to contain `: `, ZIP extraction, encoding detection, de-duplication.
Output records: sent_at (naive string as parsed, YYYY-MM-DD HH:MM:SS), sender, text (wrap_untrusted source "file"), line_no, source "whatsapp-export", provenance (sha256 of file name, line_no, date_order).

## Update 2026-11-12 (lead): exact supported layouts and unresolved reporting - TESTS_NOT_RUN
Supported (observed in exports, NOT official; 24-hour clock only):
- A `[dd/mm/yyyy, hh:mm:ss] Name: text` and B `dd/mm/yyyy, hh:mm - Name: text`; '/' or '.' separators; 2- or 4-digit year; comma after the date optional;
  seconds optional; a leading invisible direction mark is stripped; continuation lines are appended to the open message; date order dmy (default) or mdy.
Not supported and reported, with the raw line preserved: AM/PM times, non-ASCII digits, year-first or '-'-separated dates, any other locale/OS layout (`unsupported_layout`);
lines that match nothing before any message (`unparsed_line`); impossible dates under the chosen order (`invalid_date`); both numbers <= 12 and different (`ambiguous_date`,
the record is kept and flagged `date_ambiguous`); system lines without "Name: " (`system_message_unclassified`: there is no verified list of WhatsApp system messages, and a
system line containing ": " cannot be told apart from a message).
Raw preservation: every record carries `raw` (its original lines, each capped at 1000 characters) and every unresolved item carries the raw line; all text is wrapped as untrusted data.
Result keys: `records`, `system_lines`, `issues`, `unresolved`, `counts`, `import_status`, `supported_layouts`, `official_format_compliance` (always False), `provenance`.
`import_status` is `UNRESOLVED_ITEMS` whenever `unresolved` is non-empty, otherwise `NO_UNRESOLVED_ITEMS_DETECTED` - never "complete": absence of detected problems is not proof the
file was imported correctly. Compilation only; no sample export was parsed.
