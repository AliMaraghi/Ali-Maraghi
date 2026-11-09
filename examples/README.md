# Offline domain examples

All scenario values and personal tasks here are **synthetic fixtures**. They are
not market research, observed user behaviour, actual income or customer demand.
The film JSON is a proposed production plan with no supplied media; its expected
output status is BLOCKED. It is not a generated film.

The importable APIs in `core/apex/domains.py` are:

- `evaluate_opportunity(OpportunityScenario(...))`: assumed GBP net-value interval,
  cash downside, time cost and unresolved evidence questions.
- `plan_day([PersonalTask(...)], available_minutes, low_energy=False)`: a bounded
  greedy schedule; contact entries require recorded consent and remain draft-only.
- `build_production_manifest([Shot(...)], [MediaAsset(...)], workspace=...)`:
  a 60–90-second timeline and metadata intake checks. Workspace defaults to the
  project directory; media outside it and symlinked paths are refused.

JSON loaders must construct `Interval` from each `{low, high}` pair and convert
`assumptions`/`evidence_refs` to tuples before constructing `OpportunityScenario`.
The fixture markers are metadata, not dataclass constructor fields. All other
domain payload keys correspond directly to dataclass fields.

The supplied loader runs these examples without hand-written setup:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -B scripts/run_examples.py all
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=core python3 -B -m apex.kernel.cli review examples/evidence_review_synthetic.json
PYTHONDONTWRITEBYTECODE=1 python3 -B scripts/smoke_kernel.py
```

The review intentionally returns exit 2 because its evidence is synthetic. The
smoke runner saves only the synthetic decision in ignored local runtime storage
and checks that a second process does not duplicate it. It does not contact any
service. Choose a new key when code/evidence changes.

Run the independent domain tests without services or installed packages:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=core python3 -B -m unittest discover -s tests -p test_domains.py -v
```

These functions perform no network or external action and do not read media
contents. Sensitive production inputs must remain in the relevant permissioned
domain; these example files contain no personal or employer data.
