# APEX session reporting rules

Cited by every session report from 2026-11-15 onward.

## Rule 1 (R4, brutal-honesty directive, 2026-11-15)

A step is **PASS** only when its gate ran and returned PASS with raw
output in the session log.

A step is **OWNER-GATED** only when the gate itself needs human input or
real data; the build portion of the step is not owner-gated and must be
built.

A step is **ENVIRONMENT-BLOCKED** only when a specific binary or
permission is missing; state the exact missing thing.

## Rule 2 (verification levels, same directive)

Every artifact is labeled with exactly one of:

- **L0** - file exists, never parsed or loaded.
- **L1** - parsed / imported successfully at least once.
- **L2** - unit-tested with synthetic fixtures (test executed).
- **L3** - integration-tested against a real local dependency (SQLite,
  filesystem, subprocess) but not against its real target.
- **L4** - executed against its real target once, output captured.

A page/app whose real target is a browser is L0 or L4. There is no L2 or
L3 for it - no amount of Node-side syntax checking or regex-matching
against its source moves it past L0. "Statically verified" is not a level
on this scale and must not appear in a report.

## Rule 3

No adjective, and no phrase from a prior session's forbidden-phrases list,
substitutes for a command and its raw output. If a claim has no attached
command and output, it is not evidence.
