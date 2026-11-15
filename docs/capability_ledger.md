# Capability ledger — Section II tool inventory

Source: the user's "CLAUDE WORK — UNIFIED COGNITIVE INTELLIGENCE & EXECUTION DIRECTIVE"
(pasted 2026-11-15), Section II's named tool catalogue. This file exists so that this
session, and every future session, reads it BEFORE claiming any Section II capability
exists, instead of re-deriving or assuming connector status from memory.

**Headline fact, stated explicitly per the owner's instruction: of every third-party
product named in Section II.B through II.G, zero are connected or authorised in this
environment as of 2026-11-15.** The only two exceptions are Claude and Claude Code
themselves (Section II.A/B) — they are the platform this session runs on, not an external
integration, so they are listed separately below and do not count toward that zero.

States used below (four, as specified):
- **authorised** — connected and usable right now, verified by an actual tool/connector in
  this session.
- **available-not-connected** — a connector/plugin for it exists in this platform's catalogue,
  but the owner has not authorised/connected it yet (shows as "needs authorization" in this
  session's own tool list).
- **possible-not-implemented** — no product-specific connector exists, but the underlying
  capability (e.g. a general web-fetch, a general scripted integration) could be built against
  a real API if the owner supplies credentials; nothing has been built.
- **unsupported** — no connector, no plugin, no path to it from this session at all today.

All rows dated 2026-11-15 (the day this ledger was created). Re-date a row only when its
actual connection status changes, verified at that time — never on a guess.

## The platform itself (not a Section II integration)

| Tool | State | Note |
|---|---|---|
| Claude | authorised | This is the model answering you. |
| Claude Code | authorised | This CLI session, running against this repo. |

## II.A — Reasoning, research, knowledge verification

| Tool | State | Note |
|---|---|---|
| ChatGPT | unsupported | No connector in this session. |
| Perplexity | unsupported | No connector in this session. |
| Gemini | unsupported | No connector in this session. |
| NotebookLM | unsupported | No connector in this session. |
| Grammarly | unsupported | No connector in this session. |

## II.B — Software development and application engineering

| Tool | State | Note |
|---|---|---|
| Cursor | unsupported | Separate editor/product; not this session. |
| Lovable | unsupported | No connector. |
| Replit | unsupported | No connector. |
| Base44 | unsupported | No connector. |
| Emergent | unsupported | No connector. |
| GitHub | available-not-connected | `plugin:github:github` is configured but failed to connect this session ("Authorization header is badly formatted"); the local `gh` CLI via Bash may work independently of this if the owner has it authenticated on this machine — that is a different path and has not been verified here. |
| Manus | unsupported | No connector. |
| Dify | unsupported | No connector. |

## II.C — Research collection, structured memory, knowledge management

| Tool | State | Note |
|---|---|---|
| Obsidian | unsupported | No connector. |
| Notion | available-not-connected | `plugin:productivity:notion` listed, requires owner authorization via `/mcp`. |
| NotebookLM | unsupported | (see II.A) |
| Apify | unsupported | No connector. |
| General scraping tools | possible-not-implemented | No product connector; a scoped scraper against a specific lawful target could be built against this session's WebFetch tool if the owner names the exact source and terms. |

## II.D — Workflow automation and agent orchestration

| Tool | State | Note |
|---|---|---|
| n8n | unsupported | No connector. |
| Make | unsupported | No connector. |
| Zapier | unsupported | No connector. |
| Dify | unsupported | (duplicate of II.B) |
| Manus | unsupported | (duplicate of II.B) |
| Lately | unsupported | No connector. |

## II.E — Sales, marketing, customer relations, business development

| Tool | State | Note |
|---|---|---|
| OpenSEO | unsupported | No connector. |
| Clay | unsupported | No connector. |
| Twenty CRM | unsupported | No connector. |
| ManyChat | unsupported | No connector. |
| Chatbase | unsupported | No connector. |
| Beehiiv | unsupported | No connector. |
| Resend | unsupported | No connector. |
| Retell AI | unsupported | No connector. |
| Grokbot | unsupported | Unverified provider/product per the directive's own caveat; unsupported regardless. |
| Apify | unsupported | (duplicate of II.C) |

## II.F — Image, video, cinematic, motion, audio production

| Tool | State | Note |
|---|---|---|
| Midjourney | unsupported | No connector. |
| Runway | unsupported | No connector. |
| Kling | unsupported | No connector. |
| Higgsfield | unsupported | No connector. |
| Veo | unsupported | No connector. |
| Sora | unsupported | No connector. |
| HeyGen | unsupported | No connector. |
| Synthesia | unsupported | No connector. |
| Descript | unsupported | No connector. |
| Opus Clip | unsupported | No connector. |
| Canva | unsupported | No connector. |
| Figma | unsupported | No connector. |
| Gamma | unsupported | No connector. |
| Napkin | unsupported | No connector. |
| Artlist | unsupported | No connector. |
| "Design" (unidentified product) | unsupported | Per the directive's own caveat, treated as unidentified until verified; unsupported regardless. |
| Mureka | unsupported | No connector. |
| ElevenLabs | unsupported | No connector. |
| Fish Audio | unsupported | No connector. |
| Diagram/mockup rendering (SVG/HTML artifacts, inline diagrams) | authorised | A real, available-today capability of this session (Anatomy Mode / Motion Design storyboards use this) - but it produces diagrams and interactive mockups, NOT rendered cinematic video, 3D models, or final production assets. Never conflate the two. |

## II.G — Publishing and editorial operations

| Tool | State | Note |
|---|---|---|
| Beehiiv | unsupported | (duplicate of II.E) |
| Lately | unsupported | (duplicate of II.D) |
| Canva | unsupported | (duplicate of II.F) |
| Gamma | unsupported | (duplicate of II.F) |
| ManyChat | unsupported | (duplicate of II.E) |
| Resend | unsupported | (duplicate of II.E) |

## Maintenance rule

Before any future session in this repository claims a Section II capability is available,
connected, or has been used, it must re-check this file and the live tool/connector list for
that session, and update this ledger with that session's actual date if the status changed.
Never assume a prior row is still accurate without re-verifying.
