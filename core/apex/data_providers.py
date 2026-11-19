"""Registry of the data providers that are actually wired into this system, with the evidence that each one works.
The manifesto's target is 130. This file lists only real, connected sources; it never pads the count. A provider is
LIVE when the record it feeds was refreshed successfully, WIRED when the code exists but there is no fresh success,
and BLOCKED when it needs a key or sign-in from the owner."""
from __future__ import annotations

TARGET = 130
# (id, domain, what it is, ledger record that proves it, credential needed or None)
PROVIDERS = [
    ("meetup_ical", "Social", "Meetup public group calendars", "events", None),
    ("bbc_business_rss", "Finance", "BBC News business headlines", "wealth", None),
    ("reed_jobs", "Career", "Reed job search API", "wealth", "reed"),
    ("tfl_status", "Operations", "TfL line status", "commute", None),
    ("land_registry_hpi", "Property", "HM Land Registry UK House Price Index", "property", None),
    ("brave_property", "Property", "Portal listing links via Brave search", "listings", "brave"),
    ("google_trends_gb", "Content", "Google Trends daily, United Kingdom", "trends", None),
    ("google_trends_us", "Content", "Google Trends daily, United States", "trends", None),
    ("google_trends_de", "Content", "Google Trends daily, Germany", "trends", None),
    ("google_trends_fr", "Content", "Google Trends daily, France", "trends", None),
    ("google_trends_es", "Content", "Google Trends daily, Spain", "trends", None),
    ("google_trends_tr", "Content", "Google Trends daily, Turkey", "trends", None),
    ("google_trends_ir", "Content", "Google Trends daily, Iran", "trends", None),
    ("google_trends_ae", "Content", "Google Trends daily, UAE", "trends", None),
    ("bank_statements", "Finance", "Owner-uploaded bank statements (9 accounts)", "spend", None),
    ("linkedin_export", "Context", "Owner's LinkedIn connections export", "graph", None),
    ("arxiv", "Strategy", "arXiv public feeds (agent A-1)", None, None),
    ("pubmed", "Research", "PubMed search (agent A-2)", None, None),
    ("crossref", "Research", "Crossref metadata", None, None),
    ("uk_contracts_finder", "Opportunity", "UK Contracts Finder notices", None, None),
    ("ted_europa", "Opportunity", "EU TED procurement notices", None, None),
    ("wikipedia", "Research", "Wikipedia API (English, Persian)", None, None),
    ("brave_institutional", "Research", "Brave search limited to institutional sites, 9 regions", None, "brave"),
    ("gmail_metadata", "Operations", "Gmail read-only metadata sync", None, "google"),
    ("google_drive_backup", "Operations", "Encrypted off-site backup to Google Drive", None, "google"),
]


def status(latest, have: dict, now: float) -> dict:
    """latest(name) -> newest record or None; have = {"reed": bool, "brave": bool, "google": bool}."""
    rows = []
    for pid, domain, label, record, cred in PROVIDERS:
        if cred and not have.get(cred):
            state = "BLOCKED"
        elif record is None:
            state = "WIRED"
        else:
            rec = latest(record)
            fresh = rec and rec.get("status") in (None, "OK") and now - rec.get("generated_at", 0) < 8 * 86400
            failed = pid.rsplit("_", 1)[-1].upper() if pid.startswith("google_trends_") else None
            if fresh and failed and any(str(f).startswith(failed + ":") for f in rec.get("feeds_failed", [])):
                fresh = False
            state = "LIVE" if fresh else "WIRED"
        rows.append({"id": pid, "domain": domain, "label": label, "state": state})
    count = {s: sum(1 for r in rows if r["state"] == s) for s in ("LIVE", "WIRED", "BLOCKED")}
    return {"target": TARGET, "connected": len(rows), **count, "rows": rows}
