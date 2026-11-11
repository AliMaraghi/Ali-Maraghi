"""Founder-declared integration targets (2026-11-11 mandate), reconciled into the
existing provider directory. Not the authoritative 130-provider inventory, which
has not been found in the repository; these are counted separately, never merged.

route: how a legitimate connection can exist at all.
  OFFICIAL_OAUTH_API    provider-run OAuth API for the account holder
  OFFICIAL_API_KEY      provider-issued key for public/own data
  OFFICIAL_API_PAID     official API whose read access is billed (needs budget approval)
  OFFICIAL_PARTNER_ONLY official access limited to approved partners/regulated firms
  REGULATED_AGGREGATOR  UK Open Banking via an authorised aggregator (finance.py)
  DATA_EXPORT_IMPORT    no personal-data API known; owner downloads their data (UK GDPR
                        access/portability) and APEX imports the file
  PUBLIC_DATA_API       public, unauthenticated or free official data service
verify=True marks classifications not yet re-checked against current provider docs.
compartment controls cross-domain use; briefing=False compartments never enter
general summaries without an explicit founder approval record.
"""

COMPARTMENTS = {
    'financial': {'briefing': True}, 'dating': {'briefing': False}, 'intimate': {'briefing': False},
    'social': {'briefing': True}, 'communication': {'briefing': True}, 'health': {'briefing': False},
    'public-intelligence': {'briefing': True}, 'commerce': {'briefing': True},
    'investment': {'briefing': True}, 'ai': {'briefing': True}, 'email': {'briefing': True},
}


def T(target, compartment, route, adapter=None, note='', verify=False):
    return {'target': target, 'compartment': compartment, 'route': route,
            'adapter': adapter, 'note': note, 'verify': verify}


EXPORT = 'No public personal-data API known; use the in-app data download / UK GDPR access request, then import.'
TARGETS = [
    # A. Financial (live state comes from finance.py receipts)
    *[T(n, 'financial', 'REGULATED_AGGREGATOR', 'finance:' + s) for n, s in [
        ('Santander UK', 'santander'), ('HSBC UK', 'hsbc'), ('Halifax', 'halifax'), ('NatWest', 'natwest'),
        ('Lloyds Bank', 'lloyds'), ('American Express UK', 'amex'), ('Capital One UK', 'capitalone')]],
    T('PayPal', 'financial', 'REGULATED_AGGREGATOR', 'finance:paypal', 'AIS only to FCA-authorised TPPs; statement import fallback.'),
    T('Argos Pay (NewDay)', 'financial', 'REGULATED_AGGREGATOR', 'finance:argospay', 'NewDay AIS API exists; product support confirmed at consent.'),
    # B. Dating
    *[T(n, 'dating', 'DATA_EXPORT_IMPORT', None, EXPORT, True) for n in ['Tinder', 'Bumble', 'Badoo', 'Happn', 'Feeld', 'Hinge']],
    # C. Adult (isolated; spending is visible only via financial transactions with explicit approval)
    *[T(n, 'intimate', 'DATA_EXPORT_IMPORT', None, EXPORT, True) for n in ['OnlyFans', 'Pornhub']],
    # D. Social / communication
    T('Facebook Pages', 'social', 'OFFICIAL_OAUTH_API', 'meta', 'Read-only managed Pages via Facebook Login (meta_connect.py).'),
    T('Instagram (professional)', 'social', 'OFFICIAL_OAUTH_API', 'meta', 'Linked professional accounts only; personal Instagram via data download.'),
    T('Threads', 'social', 'OFFICIAL_OAUTH_API', None, 'Threads API (Meta) for own profile/posts/insights; not implemented.', True),
    T('TikTok', 'social', 'OFFICIAL_OAUTH_API', None, 'Login Kit / Display API need app review; not implemented.', True),
    T('LinkedIn', 'social', 'OFFICIAL_PARTNER_ONLY', None, 'Sign-in profile basics are open; posts/connections need partner programmes; data download available.', True),
    T('X', 'social', 'OFFICIAL_API_PAID', None, 'Read access is billed; requires founder budget approval before any call.', True),
    T('YouTube', 'social', 'OFFICIAL_OAUTH_API', None, 'YouTube Data API v3 with free quota; can reuse the Google OAuth client.', True),
    T('Reddit', 'social', 'OFFICIAL_OAUTH_API', None, 'OAuth personal app; subject to Reddit API terms; not implemented.', True),
    T('Snapchat', 'social', 'DATA_EXPORT_IMPORT', None, EXPORT, True),
    T('WhatsApp', 'communication', 'DATA_EXPORT_IMPORT', None, 'Personal chats: per-chat export only. Cloud API is for business numbers.', True),
    T('Telegram', 'communication', 'OFFICIAL_OAUTH_API', None, 'Official client API (api_id) can read own chats; full-account power needs separate security review.', True),
    T('Discord', 'communication', 'DATA_EXPORT_IMPORT', None, 'OAuth gives identity/servers only; apps cannot read user DMs; data package export.', True),
    T('Gmail', 'email', 'OFFICIAL_OAUTH_API', 'google', 'Read-only metadata sync (gmail_sync.py).'),
    # E. Health (segregated)
    T('NHS App / GP record', 'health', 'OFFICIAL_PARTNER_ONLY', None, 'No individual patient API; NHS login partner onboarding only. View/download in NHS App then import documents.', True),
    T('Hospital & specialist letters', 'health', 'DATA_EXPORT_IMPORT', None, 'Subject access request / letters imported as documents.', True),
    T('Wearables (Fitbit, Oura, Apple Health, Garmin)', 'health', 'OFFICIAL_OAUTH_API', None, 'Fitbit/Oura OAuth; Apple Health XML export; Garmin partner programme.', True),
    # F. Public intelligence
    T('GOV.UK Content API', 'public-intelligence', 'PUBLIC_DATA_API', None, '', True),
    T('UK Parliament (Bills, Hansard)', 'public-intelligence', 'PUBLIC_DATA_API', None, '', True),
    T('legislation.gov.uk', 'public-intelligence', 'PUBLIC_DATA_API', None, '', True),
    T('International news (RSS, attributable)', 'public-intelligence', 'PUBLIC_DATA_API', 'rss', 'Existing rss.py; publisher terms per feed.'),
    # G. Commerce
    T('Companies House', 'commerce', 'OFFICIAL_API_KEY', None, 'Free API key.', True),
    T('Contracts Finder / Find a Tender', 'commerce', 'PUBLIC_DATA_API', 'procurement', 'Existing connectors with real field traces.'),
    T('TED (EU tenders)', 'commerce', 'PUBLIC_DATA_API', 'procurement', 'Existing connector with real field trace.'),
    T('HMRC trade statistics (uktradeinfo)', 'commerce', 'PUBLIC_DATA_API', None, '', True),
    T('Crossref (research metadata)', 'commerce', 'PUBLIC_DATA_API', 'crossref', 'Existing provider with live receipt.'),
    # H. Investment
    T('Brokerage accounts (founder to name)', 'investment', 'OFFICIAL_API_KEY', None, 'Broker not yet identified; read-only keys only; no trading.', True),
    T('Market data (delayed)', 'investment', 'OFFICIAL_API_KEY', None, 'Must label delayed vs live; provider not selected.', True),
    # I. AI services
    T('Anthropic API', 'ai', 'OFFICIAL_API_PAID', None, 'Separately billed; Claude Max is not API credit. Requires explicit budget.'),
]


def live_evidence(ledger):
    """Derive state only from durable receipts; never from adapter existence."""
    evidence = {}
    for r in ledger.records('personal'):
        key, p = r['key'], r['payload']
        if key.startswith('google-sync-') and p.get('status') == 'PAGE_SYNCHRONIZED':
            evidence['google'] = ('LIVE', r['seq'])
        elif key.startswith('meta-pages-') and p.get('state') == 'PAGE_SYNCHRONIZED':
            evidence['meta'] = ('LIVE', r['seq'])
        elif key.startswith('finance-') and p.get('slug'):
            slug = 'finance:' + p['slug']
            if p.get('phase') == 'AIS_RETRIEVAL' and p.get('http_verified_accounts', 0) > 0:
                evidence[slug] = ('LIVE', r['seq'])
            elif p.get('phase') == 'STATEMENT_IMPORTED' and evidence.get(slug, ('',))[0] != 'LIVE':
                evidence[slug] = ('IMPORTED_STATEMENT', r['seq'])
            elif p.get('phase') == 'LOCALLY_DISCONNECTED':
                evidence[slug] = ('DISCONNECTED', r['seq'])
    for r in ledger.records('opportunity'):
        if r['key'].startswith('provider-probe-') and r['key'].endswith('-result') and r['payload'].get('provider_id') == 'crossref':
            evidence['crossref'] = ('LIVE_PUBLIC_RECEIPT', r['seq'])
    return evidence


def directory(ledger):
    evidence = live_evidence(ledger)
    rows = []
    for t in TARGETS:
        state, seq = evidence.get(t['adapter'], (None, None))
        if state is None:
            if t['adapter'] in ('procurement', 'rss'):
                state = 'EXISTING_PUBLIC_CONNECTOR'
            elif t['adapter']:
                state = 'IMPLEMENTED_NOT_AUTHORIZED'
            elif t['route'] == 'DATA_EXPORT_IMPORT':
                state = 'IMPORT_NOT_IMPLEMENTED'
            elif t['route'] == 'OFFICIAL_API_PAID':
                state = 'BLOCKED_BUDGET_APPROVAL'
            else:
                state = 'NOT_IMPLEMENTED'
        rows.append({**t, 'state': state, 'receipt_seq': seq,
                     'briefing_default': COMPARTMENTS[t['compartment']]['briefing'],
                     'inventory': 'FOUNDER_DECLARED_NOT_AUTHORITATIVE_130'})
    return rows
