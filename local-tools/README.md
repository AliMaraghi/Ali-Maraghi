# Local Tools

Four small, independently useful tools, extracted from a larger project after it turned out
the "autonomous OS" framing that project started with wasn't buildable responsibly with
current LLM technology. No 3D avatar, no voice interface, no "Swarm," no unattended automation
of anything. Each tool does exactly what it says, you click a button, you read the result.

## What's here

1. **Dating Drafts** - paste a dating-profile bio, get 3 respectful opening messages. You copy
   and send them yourself, from your own device, inside whatever app you use. This tool never
   logs into, automates, or touches any dating platform.
2. **Bank CSV Categorizer** - upload your own bank statement export (CSV), get a spend
   breakdown by category (Groceries, Transport, Bills, etc.). The totals are computed by plain
   arithmetic in Python; only the category label for each transaction comes from the LLM. The
   file is parsed in memory for one request and never stored.
3. **UK ESPP Tax Calculator** - pure arithmetic (no LLM call at all) against a UK income-tax
   rules table you supply, with a source and verification date. Not tax advice - see the
   disclaimer the tool itself prints with every result.
4. **AI Papers** - fetches the latest titles from a small, fixed list of public arXiv/MIT News
   feeds. Free, no account, no LLM call.

## What this deliberately does NOT do

- No automated sending of anything, to any platform.
- No bank OAuth, no TrueLayer/Plaid integration, no account linking.
- No "autonomous" loop, no scheduler, no cron job acting on your behalf.
- No fabricated scores ("Respect Score: 9/10", etc.) - nothing here invents a number it can't
  actually justify.
- No 3D scene, webcam, microphone, or avatar.

## Running it

You need [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed (Windows
or Mac) and an [Anthropic API key](https://console.anthropic.com/) (only needed for the Dating
and CSV tools - the Tax Calculator and AI Papers tool work without one).

```bash
cd local-tools
cp env.example .env
# edit .env and paste your real ANTHROPIC_API_KEY
docker-compose up
```

Then open **http://localhost:5173** in your browser.

To stop it: `Ctrl+C`, then `docker-compose down`.

## Cost safety

Every call to the Dating or CSV tool counts against a daily cap (`MAX_CALLS_PER_DAY` in `.env`,
default 100/day combined across both tools). This is a simple local JSON counter, not a
real-time circuit breaker - it resets each UTC day and is meant to stop an accidental loop from
running up a bill overnight, not to be a precise spend tracker. Check your own Anthropic
console for actual billing.

## Project layout

```
local-tools/
  backend/
    main.py              # FastAPI app wiring the 4 tools together
    dating.py             # Tool 1
    csv_parser.py          # Tool 2
    tax_calculator.py       # Tool 3
    rss_fetcher.py           # Tool 4
    anthropic_client.py       # minimal Anthropic Messages API client (stdlib only)
    budget_guard.py            # daily call cap
    Dockerfile
    requirements.txt
  frontend/
    src/App.jsx            # the whole UI - 4 tabs, no routing library needed
    Dockerfile
    package.json
  docker-compose.yml
  .env.example
```

Each backend tool module (`dating.py`, `csv_parser.py`, `tax_calculator.py`, `rss_fetcher.py`)
has no dependency on the others, or on FastAPI - you can import and call any one of them
directly from a plain Python script if you don't want the web UI at all.
