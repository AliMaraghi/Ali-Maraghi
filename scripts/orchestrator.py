"""Intent router for the voice-chat backend (scripts/voice_api.py).

No langgraph/langchain: neither is installed, both would need `pip install --break-system-
packages` on this Debian-managed Python, and the actual job here - classify one short utterance
into one of three labels - does not need a graph framework. Small, auditable keyword router.

Five intents:
  CASUAL_CHAT      -> the caller's existing LLM+history+semantic-recall flow (this module does not
                      call Anthropic itself; it hands back a label and voice_api.py keeps doing
                      the budget-gated call it already does).
  SYSTEM_STATUS    -> reads real data already in the ledger: today's voice-API spend, the most
                      recent agent runs, and (if the utterance is finance-flavoured) the latest
                      real A-8 financial scenario. Never fabricates a number.
  MEDIA_GENERATION -> declined for a concrete, stated reason: no Runway/ElevenLabs key is
                      configured and none is added silently. Returns NOT_CONFIGURED, not a
                      fabricated success.
  RESEARCH_REQUEST -> connects Voice to A-2 (core/apex/agents_research.py), deliberately NOT by
                      running A-2's multi-call LLM pipeline synchronously inside the HTTP request
                      (that is 3-5 sequential paid calls, each up to the Anthropic client's own
                      timeout - a bad fit for a voice turn, and the kind of "keep the model running
                      until it's done" shape the project has already walked back from once with
                      swarm_worker.py). Instead this only appends the topic to the same owner-
                      reviewed runtime/inbox/research_topics.json A-2 already reads from its normal
                      scheduled cycle (AgentRunner, durable-stop applies) and replies immediately.
                      Idempotent: a topic already present (any status) is not re-queued, so repeating
                      the same voice request cannot multiply pending/billed research runs.
  JOB_CV_REQUEST   -> reads the most recent real A-5 (Career & Industry) run from the ledger.
                      Unlike A-2, A-5 is a free/local agent that already runs on its own fixed
                      schedule (worker_loop.py/agents_runner.py) reading runtime/inbox/jobs.json
                      every cycle - there is nothing to queue here, only the latest result to
                      report, same read-only pattern as the finance branch of SYSTEM_STATUS below.
  TWITTER_DRAFT_REQUEST -> connects Voice to A-20 (core/apex/twitter_agent.py). Unlike research,
                      this is a single budget-gated LLM call (comparable latency to a normal
                      CASUAL_CHAT reply), so it DOES run synchronously inside the voice turn - but
                      it only ever calls twitter_agent.generate_and_save_draft(), which has no
                      function anywhere that posts to X. The result is a saved draft, never a
                      "sent" tweet; the reply says exactly that.

Does NOT use scripts/mcp_manager.py. That module wires an unrestricted MCP fetch server (it can
retrieve any URL, including constructing Google search URLs) directly callable by the LLM as a
tool - that is the same scraping/open-web-search capability declined earlier in this project
under a different name, and this orchestrator does not reintroduce it.
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))

CASUAL_CHAT = "CASUAL_CHAT"
SYSTEM_STATUS = "SYSTEM_STATUS"
MEDIA_GENERATION = "MEDIA_GENERATION"
RESEARCH_REQUEST = "RESEARCH_REQUEST"
JOB_CV_REQUEST = "JOB_CV_REQUEST"
ACADEMIC_NEWS_REQUEST = "ACADEMIC_NEWS_REQUEST"
DATING_DRAFT_REQUEST = "DATING_DRAFT_REQUEST"
TWITTER_DRAFT_REQUEST = "TWITTER_DRAFT_REQUEST"
FINANCE_STRATEGY_REQUEST = "FINANCE_STRATEGY_REQUEST"

_STATUS = re.compile(r"\b(status|how (are|is) (you|things|it)|what.?s (going on|happening)|"
                      r"system|agents?\b.*(run|running|status)|budget|spend|spent|cost|"
                      r"espp|tax|salary|paycheck|pay rise|finance|financial|net pay|take.?home|nic|national insurance)\b", re.I)
_MEDIA = re.compile(r"\b(video|runway|render me|animate|film|clip|image generat|picture of)\b", re.I)
_RESEARCH = re.compile(r"\b(research|look up|pubmed|find (me )?(some )?papers?|scientific (evidence|literature|studies?)|"
                        r"any studies|is there (any )?evidence)\b", re.I)
_JOB_CV = re.compile(r"\b(job|jobs|cv|r[ée]sum[ée]|career|vacanc(y|ies)|job search|shortlist|application)\b", re.I)
_ACADEMIC_NEWS = re.compile(r"\b(academic news|academic (center|centre|update)|university news|"
                             r"papers from mit|mit news|research feed)\b", re.I)
_DATING_DRAFT = re.compile(r"\b(opening message|dating opener|opener for (this|her|his|their) profile|"
                            r"write (an|a) opener)\b", re.I)
_TWITTER_DRAFT = re.compile(r"\b(draft|write|compose)\b.*\b(tweet|post on x|x post)\b|\btweet about\b", re.I)
_FINANCE_CHAIN = re.compile(r"(espp strategy|financial strategy|strategic (advice|recommendation).*(espp|finance|financial)|"
                             r"analy[sz]e my (espp|finances?)|run the finance chain)", re.I)
MAX_TOPIC_CHARS = 300


# Capability registry for the LLM-as-router fallback below: a FIXED, reviewed menu. The LLM
# never executes anything from this - it only ever picks one name (or none), exactly like
# Cloudflare's own search()/execute() two-tool pattern (a flexible CHOICE over a closed, safe
# list, never free-form code or action). Every name here already has a fully reviewed handler in
# route() below; adding a capability here without a handler would be a bug, not a feature.
_CAPABILITY_REGISTRY = {
    RESEARCH_REQUEST: "Queue a PubMed scientific-literature research request for A-2 (runs on its own schedule, not instantly).",
    JOB_CV_REQUEST: "Report the latest real A-5 job-shortlist run (reads owner-supplied runtime/inbox/jobs.json).",
    FINANCE_STRATEGY_REQUEST: "Calculate the owner's real ESPP/tax/UC/mortgage scenario (A-8) plus one LLM-generated strategic recommendation.",
    ACADEMIC_NEWS_REQUEST: "Fetch real, live arXiv/MIT News article titles right now, optionally filtered by the owner's stated interests.",
    TWITTER_DRAFT_REQUEST: "Draft a tweet/X post for the owner to review and send themselves - never posts automatically.",
    DATING_DRAFT_REQUEST: "Generate 3 respectful dating-app opening messages from a pasted profile bio - never logs in or sends anything.",
    SYSTEM_STATUS: "Report real system status: today's voice-API spend and the most recent agent runs.",
}


def llm_route(text: str, budget) -> str | None:
    """Fallback classifier for phrasing the fixed regexes below don't catch. Budget-gated like
    every other LLM call here; zero-budget-by-default still applies. A denial, upstream failure,
    or an answer outside the fixed menu all resolve to None (-> CASUAL_CHAT), never raised to the
    caller - a broken router must never block ordinary conversation."""
    from apex.agents_research import call_anthropic, load_api_key, ResearchPipelineError
    from apex.kernel.budget import BudgetDenied
    menu = "\n".join(f"- {name}: {desc}" for name, desc in _CAPABILITY_REGISTRY.items())
    key = f"voice.router.{int(time.time() * 1000)}"
    try:
        budget.reserve(key, "core", "anthropic", "intent-router-step", 1)
        api_key = load_api_key()
        choice = call_anthropic(
            api_key,
            "Pick EXACTLY ONE name from this fixed list that matches the user's request, or the "
            "single word NONE if nothing fits. Reply with ONLY that one word/name, nothing else.\n" + menu,
            text, max_tokens=20)
        budget.settle(key, 1)
    except (BudgetDenied, ResearchPipelineError):
        try:
            budget.release(key)
        except Exception:
            pass
        return None
    choice = choice.strip().splitlines()[0].strip()
    return choice if choice in _CAPABILITY_REGISTRY else None


def classify(text: str, budget=None) -> str:
    if _MEDIA.search(text):
        return MEDIA_GENERATION
    if _TWITTER_DRAFT.search(text):
        return TWITTER_DRAFT_REQUEST
    if _FINANCE_CHAIN.search(text):
        return FINANCE_STRATEGY_REQUEST
    if _ACADEMIC_NEWS.search(text):
        return ACADEMIC_NEWS_REQUEST
    if _DATING_DRAFT.search(text):
        return DATING_DRAFT_REQUEST
    if _RESEARCH.search(text):
        return RESEARCH_REQUEST
    if _JOB_CV.search(text):
        return JOB_CV_REQUEST
    if _STATUS.search(text):
        return SYSTEM_STATUS
    if budget is not None:
        routed = llm_route(text, budget)
        if routed:
            return routed
    return CASUAL_CHAT


def queue_research_topic(root: Path, text: str) -> str:
    """Append to the same owner-reviewed file A-2 reads (runtime/inbox/research_topics.json).
    Idempotent on the normalised topic text; never calls Anthropic, never touches Budget - that
    only happens later, inside agents_research.py's own scheduled, budget-gated run."""
    topic = _RESEARCH.sub("", text, count=1).strip(" :,-").strip()[:MAX_TOPIC_CHARS] or text[:MAX_TOPIC_CHARS]
    inbox = root / "runtime" / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    path = inbox / "research_topics.json"
    topics = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else []
    if not isinstance(topics, list):
        raise ValueError("research_topics.json must be a JSON list")
    normalised = topic.strip().lower()
    if any(isinstance(t, dict) and isinstance(t.get("topic"), str) and t["topic"].strip().lower() == normalised
           for t in topics):
        return "ALREADY_QUEUED"
    topics.append({"topic": topic, "status": "pending", "source": "voice", "queued_at": time.time()})
    path.write_text(json.dumps(topics, ensure_ascii=False, indent=2), encoding="utf-8")
    return "QUEUED"


def _latest_financial_summary(ledger) -> str | None:
    rows = ledger.db.execute(
        "SELECT payload FROM events WHERE kind='decision' ORDER BY seq DESC LIMIT 500").fetchall()
    for (payload,) in rows:
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            continue
        if data.get("event") == "agent_run" and data.get("agent") == "A-8":
            if data.get("status") != "OK" or not data.get("claims"):
                return None
            return (f"Your most recent ESPP scenario (confidence {data.get('confidence')}): "
                     f"{data['claims']} claim(s) recorded - open /reports on the console for the exact figures.")
    return None


def _latest_career_summary(ledger) -> str | None:
    rows = ledger.db.execute(
        "SELECT payload FROM events WHERE kind='decision' ORDER BY seq DESC LIMIT 500").fetchall()
    for (payload,) in rows:
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            continue
        if data.get("event") == "agent_run" and data.get("agent") == "A-5":
            if data.get("status") != "OK" or not data.get("claims"):
                return None
            return (f"Your most recent job search pass shortlisted {data['claims']} listing(s) "
                     f"(confidence {data.get('confidence')}) - open /console to see them. "
                     f"Nothing is ever applied to automatically.")
    return None


def _latest_strategic_summary(ledger) -> str | None:
    rows = ledger.db.execute(
        "SELECT payload FROM events WHERE kind='decision' ORDER BY seq DESC LIMIT 500").fetchall()
    for (payload,) in rows:
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            continue
        if data.get("event") == "agent_run" and data.get("agent") == "A-1":
            if data.get("status") != "OK" or not data.get("claims"):
                return None
            return (f"Your most recent feed scan (confidence {data.get('confidence')}): "
                     f"{data['claims']} claim(s) recorded from the arXiv and MIT News feeds - "
                     f"open /console for the actual titles.")
    return None


def dating_draft_reply(budget, text: str) -> tuple[str, list]:
    """Pure text-in/LLM-out (scripts/dating_agent.py) - no browser, no login, no storage of the
    pasted profile text (processed in-memory for this one call only, per that file's own
    docstring). budget is the CALLER's live Budget - no second writable connection opened."""
    import dating_agent
    from apex.agents_research import call_anthropic, load_api_key, ResearchPipelineError
    profile_text = _DATING_DRAFT.sub("", text, count=1).strip(" :,-").strip() or text
    try:
        drafts = dating_agent.generate_openers(budget, profile_text)
    except dating_agent.ResearchPipelineError as exc:
        return f"Couldn't generate openers ({exc}).", []
    steps = ["Dating assistant: generated 3 openers (1 LLM call, nothing stored or sent)"]
    # Second LLM call, same model self-rating its own output - this is NOT an independent or
    # validated measurement, just another LLM's opinion, and is labelled that way everywhere it's
    # shown (never "Respect Score: 9.2/10" presented as ground truth). Costs a second reservation.
    key = f"voice.datingjudge.{int(time.time() * 1000)}"
    try:
        budget.reserve(key, "core", "anthropic", "dating-draft-step", 1)
        judge_key = load_api_key()
        verdict = call_anthropic(
            judge_key,
            "Rate these 3 draft opening messages for respectfulness and non-generic engagement, "
            "1-10. Reply with just the lowest of the three scores, as a single integer, then a "
            "4-word reason.", drafts, max_tokens=30)
        budget.settle(key, 1)
        steps.append(f"Self-rated by the same model (not an independent score): {verdict.strip()}")
    except Exception:
        # The self-rating is optional polish - never let its failure hide the real drafts above.
        try:
            budget.release(key)
        except Exception:
            pass
    return drafts, steps


def _load_interests(root: Path) -> list:
    path = root / "runtime" / "inbox" / "interests.json"
    if not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list) or not all(isinstance(x, str) for x in data):
        raise ValueError("interests.json must be a JSON list of strings")
    return data[:20]


def _fetch_titles(fetch) -> list:
    """Direct fetch+parse of every configured feed (same allowlisted hosts A-1 itself uses) to
    get real (title, link, feed) tuples - StrategicIntelligence.run()'s own contract only exposes
    per-feed counts and a "frequent terms" claim, not individual titles, so personalizing the
    voice reply needs this separate, equally-bounded read."""
    from apex import rss
    out = []
    for name, url in rss.SOURCES.items():
        try:
            for title, link in rss.extract_items(fetch(url), limit=10):
                out.append({"title": title, "link": link, "feed": name})
        except Exception:
            continue  # a dead/blocked feed is evidence of nothing, not a crash - same as A-1 itself
    return out


def academic_news_reply(root: Path, fetch=None, budget=None) -> tuple[str, list]:
    """Runs A-1 fresh (free, no LLM, GET-only to the 3 allowlisted RSS hosts in
    core/apex/sources/public_http.py) so the reply names REAL, just-fetched article titles -
    not a stale count from the last scheduled run. Safe to run synchronously in a voice turn for
    the same reason A-8's chain is: no paid call involved. `fetch` is injectable for tests - real
    callers get the real agents_runner.fetch_public (live network), tests pass a fake.

    If the owner has populated runtime/inbox/interests.json (a plain JSON list of strings they
    wrote themselves - never inferred, never guessed), ONE extra budget-gated LLM call filters
    the real titles above against those stated interests and says plainly if nothing matches -
    it never invents relevance. Without that file, the reply stays the generic, honest "all
    titles from these N feeds" summary and says how to personalize it."""
    from apex.agents_impl import StrategicIntelligence
    from apex.agents_runtime import AgentContext
    if fetch is None:
        import agents_runner  # scripts/agents_runner.py - already on sys.path (ROOT/"scripts")
        fetch = agents_runner.fetch_public
    now = time.time()
    ctx = AgentContext(now=now, today=time.strftime("%Y-%m-%d", time.gmtime(now)),
                        inbox=root / "runtime" / "inbox", rules=root / "runtime" / "rules", fetch=fetch)
    result = StrategicIntelligence().run(ctx)
    claims = result.contract["claims"]
    if not claims:
        return (("Couldn't reach any academic feed just now - " + "; ".join(result.contract["unknowns"])),
                ["A-1: Live fetch attempted, no feed reachable"])

    interests = _load_interests(root)
    personalization_failed = False
    if interests and budget is not None:
        titles = _fetch_titles(fetch)
        if not titles:
            return "Feeds responded but no usable titles came back just now.", ["A-1: Live fetch returned nothing parseable"]
        from apex.agents_research import call_anthropic, load_api_key, ResearchPipelineError
        listing = "\n".join(f"- {t['title']} ({t['feed']})" for t in titles)
        key = f"voice.academicpersonalize.{int(now * 1000)}"
        try:
            budget.reserve(key, "core", "anthropic", "academic-personalize-step", 1)
            api_key = load_api_key()
            personalized = call_anthropic(
                api_key,
                "The owner's stated interests are: " + "; ".join(interests) + ". From the real article "
                "titles below, name only the ones actually relevant to those interests (title + one "
                "reason each). If none are relevant, say so plainly - never force a connection.",
                listing, max_tokens=300)
            budget.settle(key, 1)
            return personalized, [f"A-1: Live-fetched {len(titles)} real titles",
                                   "A-1-style: Filtered against runtime/inbox/interests.json (1 LLM call)"]
        except Exception:
            try:
                budget.release(key)
            except Exception:
                pass
            personalization_failed = True
            # Personalization failing must never hide the real generic data below.

    headline = claims[-1]["text"] if len(claims) > 1 else claims[0]["text"]  # "frequent title terms" claim if present
    feed_summaries = "; ".join(c["text"] for c in claims if c["text"].startswith("Feed '"))
    generic_reply = f"{feed_summaries}. {headline}" if feed_summaries else headline
    if not interests:
        generic_reply += (" This is generic - not tailored to you. Add runtime/inbox/interests.json "
                           "(a JSON list of topics you care about, written by you) to get a filtered, "
                           "personalized version instead.")
    elif personalization_failed:
        generic_reply += " (This is the generic version - personalizing against your interests.json failed this time.)"
    return generic_reply, [f"A-1: Live-fetched {len(result.contract['evidence'])} real article(s) just now (free, no LLM)"]


def academic_latest_titles(root: Path, fetch=None, limit: int = 10) -> list:
    """Structured sibling of academic_news_reply, for the dashboard's Academic modal: a real,
    fresh live fetch (same _fetch_titles call, same allowlisted hosts), returned as data instead
    of prose. There is no stored "latest titles" anywhere in the ledger - A-1's scheduled run
    only ever persists per-feed COUNTS (see StrategicIntelligence.run in agents_impl.py), never
    the individual titles - so "latest" here honestly means "fetched just now", not "from
    storage". A dead/blocked feed is dropped silently by _fetch_titles itself, same as elsewhere."""
    if fetch is None:
        import agents_runner
        fetch = agents_runner.fetch_public
    titles = _fetch_titles(fetch)
    # Round-robin across sites so one feed (arXiv is read first and returns 10) cannot fill the
    # whole list: before this, the dashboard showed arXiv only.
    by_site = {}
    for item in titles:
        by_site.setdefault(item["feed"].split("-")[0], []).append(item)
    mixed = []
    while any(by_site.values()):
        for queue in by_site.values():
            if queue:
                mixed.append(queue.pop(0))
    return mixed[:max(0, min(limit, 50))]


def job_cv_reply(root: Path) -> str:
    from apex.kernel.memory import Ledger
    with Ledger.read_only(root) as ledger:
        summary = _latest_career_summary(ledger)
    if summary:
        return summary
    return ("No job shortlist has been produced yet. A-5 (Career & Industry) reads "
            "runtime/inbox/jobs.json on its own 6-hour schedule - add listings there "
            "(exported from a job-alert email, never scraped) and check back after its next run.")


_AGENT_META = {
    "A-3": {"name": "Evidence & Verification", "interval": 24 * 3600,
            "task": "Scanning the fact store for genuine contradictions",
            "workflow": ["Read every (subject, predicate) pair in the fact store (facts.py)",
                         "Flag pairs with more than one distinct asserted value",
                         "Resolve nothing, pick no value as correct - a human judges",
                         "No LLM call, no network - free, rule-based"]},
    "A-1": {"name": "Strategic Intelligence", "interval": 3600,
            "task": "Monitoring public arXiv feeds for macro/AI trends",
            "workflow": ["Fetch arXiv + MIT News RSS (urllib, allowlisted hosts)", "Parse titles (xml.etree)",
                         "Count frequent title terms", "No LLM call - free, rule-based"]},
    "A-2": {"name": "Scientific Research", "interval": 24 * 3600,
            "task": "PubMed research pipeline (Planner -> Researcher -> Executor -> Critic)",
            "workflow": ["Planner: break topic into sub-questions (LLM)", "Researcher: PubMed esearch/efetch (real API)",
                         "Executor: draft brief citing only returned PMIDs (LLM)",
                         "Critic: approve or request one revision (LLM)"]},
    "A-5": {"name": "Career & Industry", "interval": 6 * 3600,
            "task": "Scoring owner-supplied job listings",
            "workflow": ["Read owner-supplied runtime/inbox/jobs.json", "Score by fixed keyword/location rules",
                         "Propose top 3 as a shortlist - never applies", "No LLM call - free, rule-based"]},
    "A-8": {"name": "Financial Intelligence", "interval": 12 * 3600,
            "task": "ESPP/tax scenario analysis",
            "workflow": ["Read owner's runtime/inbox/espp_inputs.json", "Read sourced runtime/rules/uk_tax_rules.json",
                         "Compute gain/tax/NIC in integer pence (no LLM)",
                         "Voice-only: +1 LLM call for a plain-language recommendation"]},
    "A-15": {"name": "Health & Longevity", "interval": 24 * 3600,
             "task": "Parsing owner-exported lab results (research aid only)",
             "workflow": ["Read owner's runtime/inbox/lab_results.txt", "Parse each line (health_labs.py, regex-based)",
                          "Restate printed reference-range comparison - never a clinical interpretation",
                          "No LLM call, no network - free, rule-based"]},
    "A-10": {"name": "Social & Relational", "interval": 3600,
             "task": "Preparing owner-reviewed relationship notes/drafts/bio checklists",
             "workflow": ["Read owner's runtime/inbox/relationship_requests.json",
                          "relationship_assist.guard() refuses automation/impersonation/session text outright",
                          "Record notes, prepare draft text, or checklist a bio - advisory only",
                          "No LLM call, no network, nothing ever sent/swiped/posted - free, rule-based"]},
}


def _blocked_reason(agent_id: str, root: Path) -> str | None:
    """A real, inspectable reason the agent has nothing to do - never a fabricated one."""
    inbox, rules = root / "runtime" / "inbox", root / "runtime" / "rules"
    if agent_id == "A-2":
        path = inbox / "research_topics.json"
        if not path.is_file():
            return "No runtime/inbox/research_topics.json"
        try:
            topics = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, ValueError):
            return "research_topics.json is malformed"
        if not any(isinstance(t, dict) and t.get("status") == "pending" for t in topics):
            return "No pending research topic queued"
        return None
    if agent_id == "A-5":
        return None if (inbox / "jobs.json").is_file() else "No runtime/inbox/jobs.json"
    if agent_id == "A-8":
        missing = []
        if not (rules / "uk_tax_rules.json").is_file():
            missing.append("rules/uk_tax_rules.json")
        if not (inbox / "espp_inputs.json").is_file():
            missing.append("inbox/espp_inputs.json")
        return "Missing: " + ", ".join(missing) if missing else None
    if agent_id == "A-15":
        return None if (inbox / "lab_results.txt").is_file() else "No runtime/inbox/lab_results.txt"
    if agent_id == "A-10":
        return None if (inbox / "relationship_requests.json").is_file() else "No runtime/inbox/relationship_requests.json"
    return None


def agent_telemetry(root: Path) -> list:
    """Read-only snapshot built ONLY from the existing agent_schedule and decision-event ledger
    tables that AgentRunner already writes (core/apex/agents_runtime.py) - never a fabricated
    'currently running' indicator. There is no live execution signal to observe here: each agent
    runs briefly on its own fixed schedule, not continuously, so "status" reflects the LAST
    completed run and whether a next run is due, not real-time activity. Spend is attributed only
    for A-2 (the only agent with a priced LLM call); the other three are free/rule-based."""
    from apex.kernel.memory import Ledger
    now = time.time()
    today_start = now - (now % 86400)
    out = []
    import sqlite3
    with Ledger.read_only(root) as ledger:
        last_runs: dict = {}
        for (payload,) in ledger.db.execute(
                "SELECT payload FROM events WHERE kind='decision' ORDER BY seq DESC LIMIT 1000"):
            try:
                data = json.loads(payload)
            except json.JSONDecodeError:
                continue
            if data.get("event") == "agent_run" and data.get("agent") not in last_runs:
                last_runs[data["agent"]] = data
        # agent_schedule/budget_reservations are created lazily (by AgentRunner/Budget on first
        # use); absent on a brand-new journal before any agent has ever run - not an error here.
        try:
            schedule = dict(ledger.db.execute("SELECT agent_id, last_run FROM agent_schedule").fetchall())
        except sqlite3.OperationalError:
            schedule = {}
        try:
            calls, spend_pence = ledger.db.execute(
                "SELECT COUNT(*), COALESCE(SUM(actual_minor), 0) FROM budget_reservations "
                "WHERE key LIKE 'A-2.%' AND state='SETTLED' AND created_at >= ?", (today_start,)).fetchone()
        except sqlite3.OperationalError:
            calls, spend_pence = 0, 0
        try:
            cap_row = ledger.db.execute(
                "SELECT cap_minor FROM budget_caps WHERE pool='core' AND period='day'").fetchone()
        except sqlite3.OperationalError:
            cap_row = None
        daily_cap_pence = cap_row[0] if cap_row else None  # None = no cap configured yet (zero-budget-by-default)
        for agent_id, meta in _AGENT_META.items():
            last = last_runs.get(agent_id)
            last_run_at = schedule.get(agent_id)
            blocked = _blocked_reason(agent_id, root)
            if last is None:
                status = "NEVER_RUN"
            elif last.get("status") in ("OK", "SKIPPED_TOO_SOON"):
                # SKIPPED_TOO_SOON never actually reaches the ledger - AgentRunner._run_agent()
                # returns before its _append() call when an agent isn't due yet (see
                # core/apex/agents_runtime.py), so this branch is defensive, not load-bearing.
                # "Last real completed run was OK, next one isn't due" is exactly what
                # due_in_seconds + interval_seconds already convey below - no separate status
                # is invented for it.
                status = "OK"
            else:
                status = "ERROR"
            due_in = max(0, meta["interval"] - (now - last_run_at)) if last_run_at is not None else None
            out.append({
                "agent_id": agent_id, "name": meta["name"], "status": status,
                "current_task": blocked or meta["task"], "blocked": blocked is not None,
                "last_run_at": last_run_at, "due_in_seconds": due_in,
                "last_confidence": last.get("confidence") if last else None,
                "last_claims": last.get("claims") if last else None,
                "last_error": last.get("error") if last else None,
                "interval_seconds": meta["interval"], "workflow": meta["workflow"],
                "spend_today_pence": spend_pence if agent_id == "A-2" else 0,
                "calls_today": calls if agent_id == "A-2" else 0,
                "daily_cap_pence": daily_cap_pence if agent_id == "A-2" else None,
                # Real, cheap-to-compute metrics only - never a fabricated score. Each is either a
                # direct file-existence check or a static count, not a live network/LLM call (that
                # stays in the synchronous voice path - academic_news_reply/finance_strategy_reply -
                # not in this endpoint, which gets polled every few seconds).
                "real_metrics": _real_metrics(agent_id, root),
            })
    return out


def _real_metrics(agent_id: str, root: Path) -> dict:
    if agent_id == "A-8":
        rules_loaded = (root / "runtime" / "rules" / "uk_tax_rules.json").is_file()
        inputs_loaded = (root / "runtime" / "inbox" / "espp_inputs.json").is_file()
        return {"hmrc_rules_loaded": rules_loaded, "espp_inputs_loaded": inputs_loaded}
    if agent_id == "A-1":
        from apex import rss
        return {"configured_feed_count": len(rss.SOURCES), "configured_feed_names": sorted(rss.SOURCES)}
    return {}


def dashboard_payload(root: Path) -> dict:
    """Minimal NOW/NEXT view for 3 domains, built ONLY from agent_telemetry()'s already-real,
    already-cheap data (no fresh LLM/network call triggered by loading or polling a dashboard -
    those stay in the synchronous voice path). Dating has no persisted state (see dating_agent.py
    - nothing is stored), so its "status" only reflects whether it's priced/ready to use, not a
    fabricated "3 drafts ready" count."""
    agents = {a["agent_id"]: a for a in agent_telemetry(root)}
    a8, a1 = agents["A-8"], agents["A-1"]

    finance_ready = a8["real_metrics"].get("hmrc_rules_loaded") and a8["real_metrics"].get("espp_inputs_loaded")
    net_gain_match = None
    import re as _re
    import sqlite3 as _sqlite3
    from apex.kernel import facts as _facts
    from apex.kernel.memory import Ledger
    espp_fact = None
    with Ledger.read_only(root) as _fact_ledger:
        try:
            espp_fact = _facts.query_fact(_fact_ledger, "owner", "finance_claim_0")
        except _sqlite3.OperationalError:
            espp_fact = None  # facts table doesn't exist yet (no voice finance request has run) - not an error
    if espp_fact:
        net_gain_match = _re.search(r"\bnet (\d+)p\b", espp_fact["object"])
    if net_gain_match:
        pounds = int(net_gain_match.group(1)) / 100
        finance_metric_en = f"Net ESPP (last run): £{pounds:,.2f}"
        finance_metric_fa = f"سود خالص ESPP (آخرین اجرا): £{pounds:,.2f}"
    elif a8["last_claims"]:
        finance_metric_en, finance_metric_fa = f"Last scenario: {a8['last_claims']} claim(s)", f"آخرین سناریو: {a8['last_claims']} مورد"
    else:
        finance_metric_en, finance_metric_fa = "No scenario run yet", "هنوز سناریویی اجرا نشده"
    finance = {
        "status": "Ready" if finance_ready else "Needs setup",
        "metric_en": finance_metric_en, "metric_fa": finance_metric_fa,
        "action_en": "View Strategy" if finance_ready else "Set Up ESPP",
        "action_fa": "مشاهده استراتژی" if finance_ready else "تنظیم ESPP",
        "workflow": [
            "Load your real HMRC ESPP/CGT rules file and ESPP inputs (no LLM, no network)",
            "Apply fixed UK tax arithmetic to the scenario (A-8, pure calculation)",
            "Include real past recorded outcomes for calibration, if any exist",
            "One LLM call only, to phrase the already-computed result in plain language",
        ],
        "judgement_logic_en": ("The pound figures are deterministic arithmetic against the rules "
            "file you provided - the LLM never calculates anything, it only paraphrases a number "
            "A-8 already produced. This is not AI judgement; it's code you can read."),
        "judgement_logic_fa": ("ارقام پوندی از محاسبات قطعی روی فایل قوانینی که خودتان وارد کرده‌اید "
            "به‌دست می‌آیند - مدل زبانی هیچ محاسبه‌ای انجام نمی‌دهد، فقط عددی را که A-8 از قبل "
            "تولید کرده، به زبان ساده بیان می‌کند. این «قضاوت هوش مصنوعی» نیست؛ کدی است که می‌توانید بخوانید."),
    }
    feed_count = a1["real_metrics"].get("configured_feed_count", 0)
    academic = {
        "status": "Updated" if a1["last_claims"] else "Never run",
        "metric_en": f"{feed_count} feeds configured" + (f" - last scan: {a1['last_claims']} item(s)" if a1["last_claims"] else ""),
        "metric_fa": f"{feed_count} فید فعال" + (f" - آخرین اسکن: {a1['last_claims']} مورد" if a1["last_claims"] else ""),
        "action_en": "Read Now", "action_fa": "خواندن فوری",
        "workflow": [
            "Fetch the configured RSS feeds live over HTTPS (free, no account, allowlisted hosts only)",
            "Parse real titles and links out of each feed response - nothing invented",
            "If you've written runtime/inbox/interests.json yourself, one extra LLM call ranks what was fetched",
            "A dead or blocked feed is reported as a gap, never silently hidden",
        ],
        "judgement_logic_en": ("This is extraction, not judgement: every title shown was actually "
            "present in a feed response from this run. The only subjective step is the optional "
            "interest ranking, and it can only reorder real items - it cannot invent an article."),
        "judgement_logic_fa": ("این یک «استخراج» است، نه «قضاوت»: هر عنوانی که نشان داده می‌شود واقعاً "
            "در پاسخ یک فید در همین اجرا وجود داشته است. تنها مرحله ذهنی، رتبه‌بندی اختیاری بر اساس "
            "علایق است که فقط می‌تواند موارد واقعی را دوباره مرتب کند - نمی‌تواند مقاله‌ای بسازد."),
    }
    from apex.kernel.memory import Ledger
    from apex.kernel.budget import Budget
    import sqlite3
    with Ledger.read_only(root) as ledger:
        try:
            price_row = ledger.db.execute(
                "SELECT 1 FROM cost_registry WHERE provider='anthropic' AND sku='dating-draft-step'").fetchone()
        except sqlite3.OperationalError:
            price_row = None
    dating_ready = price_row is not None
    dating = {
        "status": "Ready" if dating_ready else "Needs setup",
        "metric_en": "On-demand - nothing stored (see dating_agent.py)",
        "metric_fa": "درخواستی - چیزی ذخیره نمی‌شود",
        "action_en": "Try It" if dating_ready else "Set Up Pricing", "action_fa": "امتحان کنید" if dating_ready else "تنظیم قیمت",
        "workflow": [
            "Read the profile text you paste - never a login, a scrape, or any platform's network",
            "One LLM call drafts 3 openers grounded only in that pasted text",
            "A second call, same model, rates its own drafts for respectfulness - a self-rating, not an audit",
            "You copy and send any draft yourself, from your own device, on your own account",
        ],
        "judgement_logic_en": ("There is no independent respect score. Any number shown is the same "
            "model grading its own output, labelled as a self-rating everywhere it appears - never "
            "presented as a verified measurement. Nothing is sent automatically; nothing is stored."),
        "judgement_logic_fa": ("هیچ امتیاز احترام مستقلی وجود ندارد. هر عددی که نشان داده می‌شود، "
            "همان مدل است که خروجی خودش را نمره می‌دهد و همیشه به‌عنوان «خودارزیابی» برچسب‌گذاری "
            "شده - هرگز به‌عنوان یک سنجش تأییدشده ارائه نمی‌شود. چیزی به‌طور خودکار ارسال یا ذخیره نمی‌شود."),
    }
    banking = {
        # Honest default, not a guess: core/apex/banking_connect.py exists (see
        # docs/apex_status/BANKING_SCAFFOLD_REPORT.md) but has no mounted web route and no
        # reviewed aggregator chosen, so there is no path by which this could ever be "Ready"
        # yet - reporting anything else here would be exactly the fabricated status this whole
        # dashboard was built to refuse.
        "status": "Needs setup",
        "metric_en": "No aggregator configured - owner consent not yet reachable from any UI",
        "metric_fa": "هیچ تجمیع‌کننده‌ای تنظیم نشده - رضایت مالک هنوز از هیچ رابط کاربری قابل دسترس نیست",
        "action_en": "Not Available Yet", "action_fa": "هنوز در دسترس نیست",
        "workflow": [
            "Owner completes real OAuth consent with a reviewed FCA-regulated AISP (not built yet)",
            "Access token stored encrypted in the existing Ledger, same pattern as Meta/Google",
            "Read-only account list only - id, display name, currency",
            "Payment Initiation is blocked at the code level (require_read_only), not just by policy",
        ],
        "judgement_logic_en": ("There is nothing to judge here yet: no transactions are fetched, "
            "nothing is categorized, and no score of any kind exists for banking. The only real "
            "claim this module can make is what it structurally refuses - moving money, and "
            "sort code / account number leaving the aggregator response."),
        "judgement_logic_fa": ("در اینجا هنوز چیزی برای قضاوت وجود ندارد: هیچ تراکنشی دریافت "
            "نمی‌شود، هیچ‌چیز دسته‌بندی نمی‌شود و هیچ نوع امتیازی برای بانکداری وجود ندارد. تنها "
            "ادعای واقعی این ماژول چیزی است که به‌صورت ساختاری رد می‌کند - انتقال پول، و خروج "
            "شماره حساب/سورت‌کد از پاسخ تجمیع‌کننده."),
    }
    # Latest daily briefing written by scripts/run_autonomous_agent.py (core/apex/agent_loop.py).
    # Read-only; None until a run has actually been recorded - never a placeholder briefing.
    try:
        from apex.agent_loop import latest_briefing
        briefing = latest_briefing(root)
    except Exception:
        briefing = None
    # Month-to-date AI spend against the code-level hard cap, and the latest Opportunity Scout
    # results. All read-only; each is None if it cannot be read or has never run.
    budget_status = scout = None
    try:
        import sqlite3
        from apex.kernel.budget import month_status_from
        from apex import local_llm
        db_path = root / "runtime" / "kernel.sqlite3"
        if db_path.is_file():
            ro = sqlite3.connect(db_path.as_uri() + "?mode=ro", uri=True, timeout=5)
            try:
                budget_status = month_status_from(ro, time.time())
            finally:
                ro.close()
            budget_status["local_model"] = local_llm.enabled()
    except Exception:
        budget_status = None
    try:
        from apex import scout_common
        scout = {"events": scout_common.latest(root, "events"), "wealth": scout_common.latest(root, "wealth"),
                 "adult": scout_common.latest(root, "adult")}
        from apex import system_health
        scout["mission"] = system_health.mission(root)
        scout["commute"] = scout_common.latest(root, "commute")
        # Spending totals from uploaded statements and the owner's weekly food limit. Totals only.
        try:
            from apex import insight, spending_rules
            spend = scout_common.latest(root, "spend")
            cap = scout_common.load_config(root).get("food_weekly_cap_pence")
            scout["spend"] = None if not spend else {
                "first_date": spend.get("first_date"), "last_date": spend.get("last_date"),
                "transaction_count": spend.get("transaction_count"), "sources": len(spend.get("sources") or {}),
                "totals": spend.get("totals"), "food_alert": spending_rules.food_alert(spend, cap),
                "spike": spending_rules.top_spike(spend), "spikes": spending_rules.category_spikes(spend)[:5],
                "payday": spending_rules.payday_effect(spend),
                "insight": {"economics": insight.economics(spend), "behaviour": insight.behaviour(spend), "graph": insight.graph(spend)},
                "checkin": scout_common.latest(root, "checkin")}
        except Exception:
            scout["spend"] = None
    except Exception:
        scout = None
    return {"finance": finance, "academic": academic, "dating": dating, "banking": banking,
            "briefing": briefing, "budget": budget_status, "scout": scout,
            "automation": automation_status(root, briefing, scout), "os": _os_latest(root), "generated_at": time.time()}


def _os_latest(root):
    try:
        from apex import scout_common
        return {"cycle": scout_common.latest(root, "os"), "trends": scout_common.latest(root, "trends"),
                "drafts": scout_common.latest(root, "content_drafts"), "people": __import__("apex.people_graph", fromlist=["x"]).summary(root)}
    except Exception:
        return None


def automation_status(root: Path, briefing, scout) -> dict:
    """What runs by itself, from records only: when each job last wrote to the journal and what
    it reported. Nothing here asks systemd or assumes a job is alive - a job that stopped simply
    shows an old time. Fields are None when a job has never recorded anything."""
    import sqlite3
    from apex import local_llm
    out = {"model": local_llm.model() if local_llm.enabled() else None, "local_model": local_llm.enabled(),
           "scout_last": None, "scout_interval": 4 * 3600, "briefing_last": None,
           "gmail": None, "backup": None}
    events = (scout or {}).get("events") or {}
    wealth = (scout or {}).get("wealth") or {}
    stamps = [x.get("generated_at") for x in (events, wealth) if isinstance(x.get("generated_at"), (int, float))]
    out["scout_last"] = max(stamps) if stamps else None
    if briefing and isinstance(briefing.get("generated_at"), (int, float)):
        out["briefing_last"] = briefing["generated_at"]
    path = root / "runtime" / "kernel.sqlite3"
    if not path.is_file():
        return out
    db = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=5)
    try:
        try:
            row = db.execute("SELECT enabled,remaining,failures,next_due FROM connector_schedules WHERE connector='gmail'").fetchone()
            if row:
                out["gmail"] = {"enabled": bool(row[0]), "remaining": row[1], "failures": row[2], "next_due": row[3]}
        except sqlite3.Error:
            pass
        try:
            row = db.execute("SELECT last_attempt,last_success,last_state,bytes FROM offsite_backup").fetchone()
            if row:
                out["backup"] = {"last_attempt": row[0], "last_success": row[1], "state": row[2], "bytes": row[3]}
        except sqlite3.Error:
            pass
    finally:
        db.close()
    return out


def _general_status(ledger, now: float) -> str:
    import sqlite3
    from apex.kernel.budget import Budget
    try:
        spent_today = Budget(ledger).spent("core", "day", now)
    except sqlite3.OperationalError:
        # A genuinely fresh ledger (before Budget's tables are ever created) is read-only here
        # (Ledger.read_only) and can't create them - real state, not an error: nothing has been
        # spent yet.
        spent_today = 0
    recent = ledger.db.execute(
        "SELECT payload FROM events WHERE kind='decision' ORDER BY seq DESC LIMIT 50").fetchall()
    last_runs = {}
    for (payload,) in recent:
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            continue
        if data.get("event") == "agent_run" and data.get("agent") not in last_runs:
            last_runs[data["agent"]] = data.get("status")
    runs_text = ", ".join(f"{agent}: {status}" for agent, status in last_runs.items()) or "no agent runs recorded yet"
    reminder = ""
    try:
        from propose_capability import recurring_gaps  # scripts/ is already on sys.path (every real entry point/test puts it there)
        gaps = recurring_gaps(ledger)
        if gaps:
            top = gaps[0]
            reminder = (f" Note: you've asked for something like \"{top['text'][:80]}\" {top['count']} times - "
                        "check /console for its pending capability proposal.")
    except Exception:
        reminder = ""  # the reminder is optional polish; its failure must never hide the real status above
    return f"Voice-API spend today: {spent_today}p. Most recent agent runs - {runs_text}.{reminder}"


def system_status_reply(root: Path, text: str) -> str:
    from apex.kernel.memory import Ledger
    now = time.time()
    with Ledger.read_only(root) as ledger:
        if _FINANCE_HINT.search(text):
            financial = _latest_financial_summary(ledger)
            if financial:
                return financial
            return ("No financial scenario has been run yet. A-8 (Financial Intelligence) needs "
                    "runtime/rules/uk_tax_rules.json and runtime/inbox/espp_inputs.json to produce one.")
        return _general_status(ledger, now)


_FINANCE_HINT = re.compile(r"\b(espp|tax|salary|paycheck|pay rise|finance|financial|net pay|take.?home|nic|national insurance)\b", re.I)


def twitter_draft_reply(budget, ledger, text: str) -> str:
    """budget/ledger are the CALLER's live objects (voice_api.py's own self.budget/self.ledger) -
    reusing them, not opening a second writable connection to the same sqlite file."""
    from apex import twitter_agent
    topic = _TWITTER_DRAFT.sub("", text, count=1).strip(" :,-").strip()[:twitter_agent.MAX_DRAFT_CHARS] or text
    run_id = f"voice.{int(time.time() * 1000)}"
    try:
        twitter_agent.generate_and_save_draft(budget, ledger, f"voice:{run_id}", topic, run_id)
    except twitter_agent.ResearchPipelineError as exc:
        return f"Couldn't generate the draft ({exc}) - nothing was posted."
    return ("Draft saved for your review - I have NOT posted anything. Check /console or the "
            "Swarm Command Center to read and send it yourself.")


def finance_strategy_reply(budget, root: Path, ledger=None) -> tuple[str, list]:
    """Runs the real A-8 (FinancialIntelligence) calculation fresh - no network, no LLM, pure
    arithmetic - then makes exactly ONE budget-gated LLM call to phrase a short recommendation.
    Safe to run synchronously in a voice turn (unlike A-2's multi-call pipeline): total added
    latency is one LLM call, the same as a normal CASUAL_CHAT reply.

    If `ledger` is given, every claim A-8 actually produced (ESPP scenario, and the optional
    UC/mortgage claims if the owner set those rules up) is written to the fact store
    (core/apex/kernel/facts.py) under subject "owner" - so a later query (e.g. the dashboard's
    finance card) can show the real last-computed figure without re-running anything, and the
    full history of past scenarios is never silently overwritten."""
    from apex.agents_impl import FinancialIntelligence
    from apex.agents_research import call_anthropic, load_api_key, ResearchPipelineError
    from apex.agents_runtime import AgentContext
    now = time.time()
    ctx = AgentContext(now=now, today=time.strftime("%Y-%m-%d", time.gmtime(now)),
                        inbox=root / "runtime" / "inbox", rules=root / "runtime" / "rules")
    result = FinancialIntelligence().run(ctx)
    claims = result.contract["claims"]
    if not claims:
        return (("No ESPP scenario could be calculated - " + "; ".join(result.contract["unknowns"]) +
                 ". Nothing was spent on this request."), ["A-8: No scenario available"])
    calibration_note = ""
    had_calibration = False
    if ledger is not None:
        from apex.kernel import facts
        # Read BEFORE writing this run's claims, so "past" means strictly prior runs.
        past_outcomes = facts.recent_outcomes_for_predicate_prefix(ledger, "owner", "finance_claim_", limit=3)
        for i, claim in enumerate(claims):
            facts.assert_fact(ledger, "owner", f"finance_claim_{i}", claim["text"], "A-8:FinancialIntelligence", now=now)
        if past_outcomes:
            had_calibration = True
            lines = [f"- \"{o['claim_text'][:150]}\" was {o['outcome']}" + (f" ({o['note']})" if o["note"] else "")
                      for o in past_outcomes]
            calibration_note = (
                "\n\nWhat happened after past recommendations (recorded by the owner, not inferred - "
                "take this into account, do not repeat a rejected approach without acknowledging it):\n"
                + "\n".join(lines))
    scenario_text = "\n".join(c["text"] for c in claims)
    key = f"voice.financestrategy.{int(now * 1000)}"
    budget.reserve(key, "core", "anthropic", "finance-strategy-step", 1)
    try:
        api_key = load_api_key()
        advice = call_anthropic(
            api_key,
            "Give one short, concrete, UK-specific strategic recommendation (2 sentences max) based "
            "ONLY on the scenario(s) below. Decision support only - never call this tax or financial "
            "advice, and say so if the scenario is too uncertain to recommend anything specific. If past "
            "outcomes are given, let them visibly change what you recommend this time.",
            f"Scenario(s):\n{scenario_text}{calibration_note}", max_tokens=150)
    except ResearchPipelineError:
        budget.release(key)
        raise
    budget.settle(key, 1)
    # These "steps" report what ACTUALLY ran, in order, in this synchronous call - not a fake
    # live-progress feed (there is no streaming; the UI shows them only once the full reply
    # arrives). See SwarmPanel.jsx / App.jsx's own comments on not fabricating activity.
    steps = [f"A-8: Calculated {len(claims)} real scenario claim(s) (free, no LLM)"]
    if had_calibration:
        steps.append(f"Calibration: included {len(past_outcomes)} real recorded outcome(s) from past runs")
    steps.append("A-1-style: Generated strategic recommendation (1 LLM call)")
    return f"{scenario_text}\nRecommendation (not tax/financial advice): {advice}", steps


def _execute_capability(intent: str, text: str, root: Path, budget, ledger, academic_fetch) -> tuple[str, list]:
    """Runs exactly ONE capability from the fixed _CAPABILITY_REGISTRY menu via its existing,
    reviewed handler. Extracted out of route() so the single-shot dispatch below and the
    sequence planner further down share the exact same code path and error handling - a
    sequence is never a second, looser way to invoke a capability."""
    if intent == TWITTER_DRAFT_REQUEST:
        if budget is None or ledger is None:
            return "Twitter drafting isn't wired up on this call path yet.", []
        from apex.kernel.budget import BudgetDenied
        try:
            reply = twitter_draft_reply(budget, ledger, text)
        except BudgetDenied as exc:
            return f"Can't draft that right now - budget denied ({exc}). Nothing was spent or posted.", []
        return reply, ["A-20: Generated draft (1 LLM call)"]
    if intent == FINANCE_STRATEGY_REQUEST:
        if budget is None:
            return "The finance strategy chain isn't wired up on this call path yet.", []
        from apex.kernel.budget import BudgetDenied
        from apex.agents_research import ResearchPipelineError
        try:
            return finance_strategy_reply(budget, root, ledger=ledger)
        except BudgetDenied as exc:
            return f"Can't run that right now - budget denied ({exc}). Nothing was spent.", []
        except ResearchPipelineError as exc:
            return f"Couldn't generate the recommendation ({exc}).", []
    if intent == SYSTEM_STATUS:
        return system_status_reply(root, text), []
    if intent == RESEARCH_REQUEST:
        result = queue_research_topic(root, text)
        if result == "ALREADY_QUEUED":
            reply = "That topic is already queued or already researched - check /console for the result."
        else:
            reply = ("Queued for A-2 Scientific Research - it runs on its normal schedule (PubMed "
                      "evidence only, budget-gated), not right now. Check /console for the draft "
                      "once it's ready; nothing is spent or published without your review.")
        return reply, ["A-2: Queued (runs on its own schedule, not now)"]
    if intent == JOB_CV_REQUEST:
        return job_cv_reply(root), []
    if intent == ACADEMIC_NEWS_REQUEST:
        return academic_news_reply(root, fetch=academic_fetch, budget=budget)
    if intent == DATING_DRAFT_REQUEST:
        if budget is None:
            return "The dating draft helper isn't wired up on this call path yet.", []
        from apex.kernel.budget import BudgetDenied
        try:
            return dating_draft_reply(budget, text)
        except BudgetDenied as exc:
            return f"Can't generate that right now - budget denied ({exc}). Nothing was spent.", []
    raise ValueError(f"_execute_capability has no handler for {intent!r} - this is a registry/dispatch bug")


_SEQUENCE_HINT = re.compile(r"\b(then|after that|and then|also)\b", re.I)


def llm_plan(text: str, budget) -> list | None:
    """The actual planner: composes an ORDERED SEQUENCE of 2-3 names from the SAME fixed
    _CAPABILITY_REGISTRY menu that llm_route picks a single name from - never a new action,
    never generated code, never more than 3 steps, never a name outside the reviewed menu. This
    is the difference between "pick one capability" and "compose capabilities into a sequence I
    didn't write by hand": the composition is real, but every element of it is still one of the
    same 7 reviewed, already-dispatchable names. Budget-gated under its own SKU; any denial,
    upstream failure, or malformed/out-of-menu answer safely resolves to None (-> caller falls
    back to the normal single-intent classify())."""
    from apex.agents_research import call_anthropic, load_api_key, ResearchPipelineError
    from apex.kernel.budget import BudgetDenied
    menu = "\n".join(f"- {name}: {desc}" for name, desc in _CAPABILITY_REGISTRY.items())
    key = f"voice.planner.{int(time.time() * 1000)}"
    try:
        budget.reserve(key, "core", "anthropic", "intent-planner-step", 1)
        api_key = load_api_key()
        raw = call_anthropic(
            api_key,
            "The user's request may need MORE THAN ONE of these fixed capabilities run in order. "
            "Reply with ONLY a comma-separated ordered list of 2 or 3 names from this exact list "
            "(no numbering, no other words), or the single word NONE if one capability (or none) "
            "is enough:\n" + menu,
            text, max_tokens=40)
        budget.settle(key, 1)
    except (BudgetDenied, ResearchPipelineError):
        try:
            budget.release(key)
        except Exception:
            pass
        return None
    raw = raw.strip().splitlines()[0].strip()
    if raw == "NONE" or not raw:
        return None
    names = [n.strip() for n in raw.split(",") if n.strip()]
    if not all(n in _CAPABILITY_REGISTRY for n in names):
        return None  # any name outside the fixed menu invalidates the whole plan - never partially act on it
    if not 2 <= len(names) <= 3:
        return None  # a single name isn't a "sequence" - the normal router already covers that case
    return names


def route(text: str, root: Path, budget=None, ledger=None, academic_fetch=None) -> dict:
    """Returns {"intent": ..., "handled": bool, "reply": str or None}.
    handled=False means the caller (voice_api.py) should run its own LLM+history+recall flow;
    handled=True means `reply` is the final answer and no Anthropic call should happen.
    budget/ledger are optional: only TWITTER_DRAFT_REQUEST needs them (a real budget-gated write);
    every other intent still only opens its own read-only connection, unchanged.

    If `budget` is given and the text hints at more than one step ("then"/"also"/"after that"),
    the planner (llm_plan) is tried first; a valid 2-3-step plan runs each capability in order
    through the exact same _execute_capability() used for a single intent, and replies/steps are
    concatenated. No plan (denied, failed, or not actually multi-step) falls through to the
    ordinary single-intent classify()/dispatch below, unchanged.
    """
    if budget is not None and _SEQUENCE_HINT.search(text):
        plan = llm_plan(text, budget)
        if plan:
            replies, all_steps = [], []
            for step_intent in plan:
                reply, steps = _execute_capability(step_intent, text, root, budget, ledger, academic_fetch)
                replies.append(f"[{step_intent}] {reply}")
                all_steps.extend(steps)
            return {"intent": "SEQUENCE:" + "+".join(plan), "handled": True,
                    "reply": "\n\n".join(replies), "steps": all_steps}
    intent = classify(text, budget=budget)
    if intent == MEDIA_GENERATION:
        return {"intent": intent, "handled": True,
                "reply": ("Media generation isn't configured - no Runway or ElevenLabs API key has "
                          "been set up, and I won't fake a result. Tell me if you want that wired up "
                          "for real, with a key you provide and a spend cap, like the voice API has."),
                "steps": []}
    if intent in _CAPABILITY_REGISTRY:
        reply, steps = _execute_capability(intent, text, root, budget, ledger, academic_fetch)
        return {"intent": intent, "handled": True, "reply": reply, "steps": steps}
    return {"intent": CASUAL_CHAT, "handled": False, "reply": None, "steps": []}
