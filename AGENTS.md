# SOPHIA AGENT — AGENTS.md

## WHAT THIS IS
AI voice acquisitions agent for a real estate wholesaling business in
San Joaquin County, California. Sophia calls and receives calls from
distressed-property sellers, qualifies them, and books walkthroughs.
Ground-up rebuild of an earlier prototype (Lavish213/rei-agent) after
an audit found core paths silently broken. Scope: manual CSV lead
import, comps/ARV/MAO calculation, a correctly-wired voice pipeline,
a dialer that works an uploaded lead list on its own (calling, then
SMS/email follow-up), a discovery worker that finds sellers on its
own by monitoring Reddit for seller-intent posts, and a dashboard.
Broader automated lead scraping (RSS/court/eviction/CRMLS/cash-buyer)
and elaborate live emotional-state tracking are deferred to a phase
2, once the core is proven on real calls.

## OWNER
Angelo Washington. Goes by Alanzo Alcarez for the business.
Business name: San Joaquin House Buyers
Business domain: sanjoaquinhousebuyers.com

## STACK
- Backend: Python 3.11, FastAPI
- Voice: SignalWire SDK + Pipecat + Deepgram (STT + TTS) + Claude API
- SMS: SignalWire. Email: SendGrid.
- Bob worker: standalone process, same repo, generates call briefs
- Dialer worker: standalone process, same repo, batch outbound calling
- Discovery worker: standalone process, same repo, polls Reddit
  (PRAW) for seller-intent posts across San Joaquin-area + real
  estate subreddits
- Database: Supabase (Postgres), RLS enabled on every table
- Dashboard: Next.js 14 (pinned), Tailwind, Supabase Auth + JS client
- Hosting: Railway (backend + bob + dialer + discovery), Vercel (dashboard)
- Phone/SMS: SignalWire only — never Twilio

## VOICE AGENT
Name: Sophia Reyes. Acquisitions coordinator for San Joaquin House
Buyers. Warm, direct, California casual. See
backend/voice/prompts/sophia_runtime.md for the full voice spec.

## CRITICAL RULES — NEVER BREAK THESE
- Never write comments in Python code — no inline, no block, no
  docstrings. SQL migrations may use `--` comments to document
  columns since they are not Python.
- Never use Twilio — SignalWire only.
- All Supabase access goes through backend/lib/db.py only. No other
  module creates a Supabase client or queries a table directly. The
  bob/ worker is the one exception — it is a separately-deployed
  process, and it imports backend.lib.db like everything else rather
  than opening its own client.
- Always `from backend.lib import db` and call `db.fn(...)` — never
  `from backend.lib.db import fn`. Importing a bare function binds it
  at import time, which silently breaks test monkeypatching and makes
  call sites harder to trace back to db.py.
- Never commit .env files, ever — not even with placeholder values.
- All money values stored as integer cents. ARV and MAO always
  integers, never floats. MAO formula: (ARV * 0.70) - 2,500,000
  (cents), i.e. a $25,000 repair buffer, both configurable via
  MAO_MULTIPLIER / MAO_REPAIR_BUFFER but defaulting to that.
- Distress score 0-100, higher = more urgent.
- Use loguru for all logging, never print().
- No business logic in API routes — routes call into backend/*
  modules and translate to/from HTTP; the module owns the logic.
- Every environment variable the code reads must be declared in
  backend/lib/config.py and mirrored in .env.example. No bare
  os.getenv/os.environ calls outside that one file.

## FILE STRUCTURE
backend/lib/db.py           → Supabase client wrapper, only DB access point
backend/lib/config.py       → single source of truth for all env vars
backend/scout/              → Propwire CSV parser + distress scorer
backend/comps/               → comp entry → ARV/MAO calculator
backend/compliance/          → TCPA/DNC/calling-hours gate
backend/voice/                → Pipecat pipeline + SignalWire + tools
backend/voice/prompts/        → Sophia's system prompt (one file)
backend/alerts/                → SMS (SignalWire) + email (SendGrid) + post-call follow-up
backend/scout/intake.py        → the one path every lead source funnels through
backend/scout/skiptrace.py     → BatchData skip trace + DNC/TCPA scrub, address to phone
backend/scout/reddit.py        → Reddit intent-scoring + fetch logic (also used by discovery/)
backend/scout/convert.py       → converts a reddit_match into a property/contact/lead
backend/api/                    → FastAPI route handlers
bob/                             → standalone call-brief worker process
dialer/                           → standalone batch-outbound-calling worker process
discovery/                        → standalone Reddit-lead-discovery worker process
dashboard/                         → Next.js app, Supabase Auth
scripts/                            → one-off scripts, never imported by backend
supabase/migrations/                 → schema files only
tests/                                 → pytest coverage for backend/*, bob/, dialer/, discovery/

## DATABASE TABLES
properties          → cached distressed properties (no phone numbers)
contacts             → skip-traced owner contact info
leads                → active pipeline leads, one per property
calls                → call records, transcripts, disposition, ended_at
transcript_chunks    → per-utterance transcript rows for a call
call_events          → structured event log for a call
comps                → comparable sales entered per property
offers               → offer drafts/status tied to a lead
dnc_list             → numbers that must never be called/texted
lead_intel_packets   → structured facts extracted across calls
decision_records     → audit trail of bob's call-brief decisions
seller_memory        → durable per-lead facts read at call start
sms_messages         → outbound + inbound SMS log
email_messages       → outbound + inbound email log
reddit_matches       → raw Reddit posts scored for seller intent, pre-lead

## OUTBOUND / FOLLOW-UP BEHAVIOR
Dropping a CSV in only ingests it — nothing is called, texted, or
emailed automatically until the dialer process picks it up. The
dialer runs on its own schedule (DIALER_INTERVAL_MINUTES), pulls due
leads (respecting opted_out/dnc_blocked/stage/reattempt interval),
checks a DB-backed active-call count against MAX_CONCURRENT_OUTBOUND
before every single dial (never an in-memory counter — that leaks
across restarts and was the old repo's outbound-calling bug), and
calls place_outbound_call, which itself re-checks compliance per
lead. After a call resolves — including a call that never connects
(no-answer/busy/failed, detected via the SignalWire status callback,
not just the websocket path) — backend/alerts/followup.py sends a
disposition-appropriate SMS and/or email. Every send re-checks
opted_out/email_opted_out immediately before sending, not just at
dial time. Inbound SMS handles STOP/START itself; there is no
separate DNC sync step required for that.

## LEAD SOURCES
Every lead, from every source, is created through one function:
backend/scout/intake.py::intake_lead. Never create property+contact+lead
rows directly in a new source module — add a source and call intake_lead,
so dedupe, phone normalization, and source scoring stay in one place.
Phone numbers are normalized to E.164 (+1XXXXXXXXXX) at intake, because
SignalWire reports E.164 while CSVs carry every other format, and an
un-normalized compare silently creates duplicate leads for one person.

Sources currently wired:
csv_import      → dashboard CSV upload (backend/scout/ingest.py)
web_form        → POST /api/intake/web-form, shared-secret header
inbound_call    → unknown caller, created in backend/voice/context.py
inbound_sms     → unknown texter, created in backend/alerts/sms.py
reddit          → discovery worker, needs manual contact-finding
skiptrace       → enrichment, not a source of new leads

A STOP text from an unknown number goes to dnc_list and does NOT create a
lead. See docs/LEAD_SOURCES.md for the full research, costs, and the
sources that were deliberately rejected (notably CA eviction records).

## LEAD DISCOVERY (REDDIT)
The discovery worker (discovery/main.py) runs on its own schedule
(REDDIT_POLL_INTERVAL_MINUTES), calls backend/scout/reddit.fetch_matches()
to pull new posts from a fixed list of San Joaquin-area + real-estate
subreddits, scores each for seller intent (hot/warm/cold/none) via
keyword matching, and inserts new ones into reddit_matches (deduped
by reddit_id). Reddit never gives a phone number, so a match is NOT a
lead and nothing is called/texted/emailed off it automatically — it
shows up on the dashboard's /discovered page for a human to review,
find contact info for (e.g. replying to the post), and convert via
POST /api/discovery/reddit-matches/{id}/convert, which creates a
property + contact + lead (backend/scout/convert.py) and links the
match back to it. Once converted, that lead flows through the normal
dialer → call → follow-up pipeline exactly like a CSV-imported lead.
Without REDDIT_CLIENT_ID/REDDIT_CLIENT_SECRET configured, the
discovery worker degrades to a no-op (get_reddit_client() returns
None) rather than erroring.

## BUILD ORDER
1. backend/lib/config.py + db.py     ← START HERE
2. supabase/migrations/0001_init.sql, 0002_outreach.sql, 0003_discovery.sql
3. backend/scout/parser.py + scorer.py
4. backend/comps/calculator.py
5. backend/compliance/compliance.py
6. backend/api/main.py + routes
7. backend/voice/webhook.py + agent.py + tools.py
8. backend/alerts/sms.py + email.py + followup.py
9. bob/ worker
10. dialer/ worker
11. backend/scout/reddit.py + convert.py, discovery/ worker
12. dashboard/ (Next.js)
13. Railway (4 processes) + Vercel deployment
