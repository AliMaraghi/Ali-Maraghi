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
    """Every inventory target with its honest state: LIVE, WIRED, BLOCKED or NOT_CONNECTED."""
    by_id, rank = {r["id"]: r["state"] for r in rows}, {"LIVE": 3, "WIRED": 2, "BLOCKED": 1}
    out, totals = {}, {"LIVE": 0, "WIRED": 0, "BLOCKED": 0, "NOT_CONNECTED": 0}
    for category, names in INVENTORY.items():
        items = []
        for name in names:
            states = [by_id[i] for i in SERVED_BY.get(name, []) if i in by_id]
            state = max(states, key=lambda x: rank[x]) if states else "NOT_CONNECTED"
            totals[state] += 1
            items.append({"name": name, "state": state})
        out[category] = items
    return {"total": sum(totals.values()), **totals, "categories": out}


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
    return {"target": TARGET, "connected": len(rows), **count, "rows": rows, "inventory": inventory(rows)}
