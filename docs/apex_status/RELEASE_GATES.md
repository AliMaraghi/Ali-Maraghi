# Release gates — no release authorized

| Gate | Current evidence | Status |
|---|---|---|
| Source retention | Original hashes; 178 groups/968 lines; all A01–A09 retained | PASS_SOURCE_TRACE_ONLY |
| Semantic scope | Both §5 sets and 18 roles retained; independent atomization absent | PARTIAL |
| Offline negative contracts | Current regression log and five rejected reference defects | TESTED_OFFLINE |
| Integration/dependencies | Two optional web tests skipped; no pinned installed staging environment | BLOCKED |
| Real value | No independently verified demand, measured productivity or rendered film | NOT TESTED |
| Recovery/stop | One synthetic SQLite restore; no production/offsite recovery or global kill drill | PARTIAL |
| Owner/release approval | No deployment authorization; no authentic approval service | BLOCKED |

Original A01–A09 and G0–G7 remain distinct in REQUIREMENTS.json. Review-kit G0–G6
labels are a separate proposed release checklist and do not renumber the original
acceptance gates. No full mission acceptance PASS is inferred from this table.
