# Health labs text parser (core/apex/health_labs.py)

Status: TESTS_NOT_RUN (py_compile only). Research aid, not a medical device. No diagnosis, advice or interpretation.
Raw health data must stay local per the specification; the module stores nothing, writes no files, makes no network calls.

Input: lab result text the owner extracted locally from a report (no PDF library). Interface:
`parse_lab_text(text, document_id, max_lines=5000) -> list[dict]`, `reference_check(result) -> dict`.
Row fields: test, value (string as printed), value_num (float), value_comparator, unit, ref_low, ref_high, ref_text,
printed_flag, flag (LOW/HIGH/NORMAL/UNKNOWN), page, line_no, document_id, needs_review.

Rules: units are never guessed (missing/odd unit -> unit None, needs_review). flag is computed only when both range ends
parse (`a - b`); `<`/`>` ranges and `<`/`>` values give UNKNOWN. Decimal-comma values keep provenance but no value. `Page N`
(optionally `of M`) lines set the page. Unrecognised lines are ignored. Synthetic example line: `Exampletest 14.2 g/dL 13.0 - 17.0`.

Not verified: this is a heuristic text format, not an official specification; real report layouts were not seen
(no real data used). Printed-flag tokens (H, L, HH, LL, HIGH, LOW, *) are recorded, not trusted.
