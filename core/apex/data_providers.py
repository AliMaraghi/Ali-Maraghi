"""Registry of the data providers that have code in this system, with the evidence each one must show.

States (never inferred from a registry entry or a bare timestamp):
  LIVE_VERIFIED  the provider's own proof is present, says success, and is inside that provider's freshness window
  IMPLEMENTED    code exists but there is no current proof of a successful retrieval
  FAILING        the latest evidence is a failure
  AUTH_REQUIRED  a key or sign-in from the owner is missing
"catalogued" is only the number of entries here; it is not a count of working connections."""
from __future__ import annotations

TARGET = 130
H = 3600
# (id, domain, label, proof, max age in seconds, credential)
# proof: ("status", record) -> record.status must be "OK"; ("field", record, key) -> that key must be non-empty;
#        ("trend", GEO) -> trends OK and GEO not in feeds_failed; ("backup",) / ("gmail",) -> automation evidence; None -> no proof wired
PROVIDERS = [
    ("meetup_ical", "Social", "Meetup public group calendars", ("status", "events"), 9 * H, None),
    ("bbc_business_rss", "Finance", "BBC News business headlines", ("field", "wealth", "alert"), 9 * H, None),
    ("reed_jobs", "Career", "Reed job search API", ("field", "wealth", "job"), 9 * H, "reed"),
    ("tfl_status", "Operations", "TfL line status", ("status", "commute"), 9 * H, None),
    ("land_registry_hpi", "Property", "HM Land Registry UK House Price Index", ("status", "property"), 8 * 24 * H, None),
    ("brave_property", "Property", "Portal listing links via Brave search", ("status", "listings"), 49 * H, "brave"),
] + [(f"google_trends_{g.lower()}", "Content", f"Google Trends daily, {g}", ("trend", g), 13 * H, None) for g in ("GB", "US", "DE", "FR", "ES", "TR", "IR", "AE")] + [
    ("bank_statements", "Finance", "Owner-uploaded bank statements (manual upload, not a bank connection)", None, 0, None),
    ("linkedin_export", "Context", "Owner's LinkedIn connections export (manual upload)", None, 0, None),
    ("arxiv", "Strategy", "arXiv public feeds (agent A-1)", None, 0, None),
    ("pubmed", "Research", "PubMed search (agent A-2)", None, 0, None),
    ("crossref", "Research", "Crossref metadata", None, 0, None),
    ("uk_contracts_finder", "Opportunity", "UK Contracts Finder notices", None, 0, None),
    ("ted_europa", "Opportunity", "EU TED procurement notices", None, 0, None),
    ("wikipedia", "Research", "Wikipedia API (English, Persian)", None, 0, None),
    ("brave_institutional", "Research", "Brave search limited to institutional sites, 9 regions", None, 0, "brave"),
    ("gmail_metadata", "Operations", "Gmail read-only metadata sync", ("gmail",), 0, None),
    ("google_drive_backup", "Operations", "Encrypted off-site backup to Google Drive", ("backup",), 49 * H, None),
]


def _judge(proof, max_age, latest, automation, now):
    """-> (state, evidence text). Only explicit success inside the window counts as LIVE_VERIFIED."""
    if proof is None:
        return "IMPLEMENTED", "no current proof of retrieval is recorded"
    kind = proof[0]
    if kind == "backup":
        b = (automation or {}).get("backup") or {}
        ok = b.get("state") == "UPLOADED" and b.get("last_success") and now - b["last_success"] <= max_age
        return ("LIVE_VERIFIED", f"uploaded {int((now - b['last_success']) // H)}h ago") if ok else ("IMPLEMENTED", "no upload inside 49h")
    if kind == "gmail":
        g = (automation or {}).get("gmail") or {}
        return ("FAILING", f"{g.get('failures')} consecutive failed sync(s)") if g.get("failures") else ("IMPLEMENTED", "no successful sync is recorded")
    rec = latest("trends" if kind == "trend" else proof[1])
    if not rec or not rec.get("generated_at"):
        return "IMPLEMENTED", "never ran"
    age = now - rec["generated_at"]
    if age > max_age:
        return "IMPLEMENTED", f"last result is {int(age // H)}h old, outside its {int(max_age // H)}h window"
    if kind == "status":
        return ("LIVE_VERIFIED", f"status OK {int(age // H)}h ago") if rec.get("status") == "OK" else ("FAILING", f"last status {rec.get('status')}")
    if kind == "field":
        return ("LIVE_VERIFIED", f"returned data {int(age // H)}h ago") if rec.get(proof[2]) else ("FAILING", "last run returned nothing from this provider")
    failed = any(str(f).startswith(proof[1] + ":") for f in rec.get("feeds_failed", []))
    return ("LIVE_VERIFIED", f"feed read {int(age // H)}h ago") if rec.get("status") == "OK" and not failed else ("FAILING", "feed failed on the last scan")


# The owner's target inventory (22 Nov 2026): 130 sources plus later additions. A target, not a claim of connection.
INVENTORY = {
    "Research and scientific evidence": ["PubMed", "Europe PMC", "Crossref", "OpenAlex", "Semantic Scholar", "arXiv", "CORE", "DOAJ", "Zenodo", "Figshare",
        "ClinicalTrials.gov", "Cochrane Library", "NICE", "NHS", "World Health Organization", "Our World in Data", "UKRI Gateway to Research", "CORDIS", "OpenAIRE", "Unpaywall"],
    "Strategy, economics and industry": ["LSE IDEAS", "Chatham House", "King's College London War Studies", "Middle East Institute", "Carnegie Middle East Center",
        "Oxford Internet Institute", "Pew Research Center", "SemiAnalysis", "Bloomberg", "Financial Times", "Data Center Dynamics", "Stronger by Science", "Examine.com",
        "Human Kinetics", "World Bank", "International Monetary Fund", "OECD", "Eurostat", "Office for National Statistics", "Bank of England"],
    "Government, procurement and regulation": ["Companies House", "SEC EDGAR", "UK Find a Tender", "UK Contracts Finder", "EU TED", "SAM.gov", "USAspending.gov",
        "legislation.gov.uk", "HM Revenue & Customs", "Financial Conduct Authority", "Information Commissioner's Office", "Department for Work and Pensions",
        "HM Land Registry", "UK Planning Data", "Energy Performance of Buildings Register", "data.gov.uk", "London Datastore", "Transport for London", "Met Office", "European Central Bank"],
    "Google ecosystem": ["Gmail", "Google Drive", "Google Docs", "Google Sheets", "Google Slides", "Google Calendar", "Google People", "Google Tasks", "Google Photos",
        "Google Maps Platform", "Google Search Console", "Google Analytics", "Google Ads", "Google Business Profile", "YouTube"],
    "Productivity and infrastructure": ["Microsoft Outlook", "Microsoft Teams", "Microsoft OneDrive", "Microsoft SharePoint", "Microsoft Planner", "Microsoft To Do",
        "Microsoft OneNote", "Microsoft Power Automate", "Notion", "Slack", "Dropbox", "Box", "Cloudflare", "IONOS", "Google Cloud"],
    "Financial and business services": ["TrueLayer", "Yapily", "Plaid", "Moneyhub", "Xero", "QuickBooks Online", "FreeAgent", "Stripe", "PayPal", "Wise"],
    "Social, professional and community": ["LinkedIn", "Facebook Pages", "Instagram Professional", "Threads", "WhatsApp Business", "TikTok", "X", "Reddit", "Pinterest",
        "Telegram", "Discord", "Buffer", "Resident Advisor", "Feeld", "Meetup"],
    "AI, creative tools and self-improvement": ["OpenAI", "Anthropic Claude", "Google Gemini", "OpenRouter", "Hugging Face", "GitHub", "GitLab", "Stack Exchange", "PyPI",
        "npm", "Context7", "Runway", "ElevenLabs", "Adobe Creative Cloud", "CometAP"],
    "Later additions": ["BBC Persian", "OnlyFans", "Binance"],
}
# inventory name -> ids of the connected providers above that serve it
SERVED_BY = {"PubMed": ["pubmed"], "Crossref": ["crossref"], "arXiv": ["arxiv"], "UK Contracts Finder": ["uk_contracts_finder"], "EU TED": ["ted_europa"],
             "HM Land Registry": ["land_registry_hpi"], "Transport for London": ["tfl_status"], "Gmail": ["gmail_metadata"], "Google Drive": ["google_drive_backup"],
             "LinkedIn": ["linkedin_export"], "Meetup": ["meetup_ical"]}


def inventory(rows: list) -> dict:
    """Every inventory target with its evidence-based state, or NOT_CONNECTED."""
    by_id, rank = {r["id"]: r["state"] for r in rows}, {"LIVE_VERIFIED": 4, "FAILING": 3, "IMPLEMENTED": 2, "AUTH_REQUIRED": 1}
    out, totals = {}, {"LIVE_VERIFIED": 0, "IMPLEMENTED": 0, "FAILING": 0, "AUTH_REQUIRED": 0, "NOT_CONNECTED": 0}
    for category, names in INVENTORY.items():
        items = []
        for name in names:
            states = [by_id[i] for i in SERVED_BY.get(name, []) if i in by_id]
            state = max(states, key=lambda x: rank[x]) if states else "NOT_CONNECTED"
            totals[state] += 1
            items.append({"name": name, "state": state})
        out[category] = items
    return {"total": sum(totals.values()), **totals, "categories": out}


def status(latest, have: dict, now: float, automation: dict | None = None) -> dict:
    """latest(name) -> newest record or None; have = {"reed": bool, "brave": bool}; automation = backup/gmail evidence."""
    rows = []
    for pid, domain, label, proof, max_age, cred in PROVIDERS:
        if cred and not have.get(cred):
            state, why = "AUTH_REQUIRED", f"{cred} key not set"
        else:
            state, why = _judge(proof, max_age, latest, automation, now)
        rows.append({"id": pid, "domain": domain, "label": label, "state": state, "evidence": why})
    count = {k: sum(1 for r in rows if r["state"] == k) for k in ("LIVE_VERIFIED", "IMPLEMENTED", "FAILING", "AUTH_REQUIRED")}
    return {"target": TARGET, "catalogued": len(rows), **count, "rows": rows, "inventory": inventory(rows)}
