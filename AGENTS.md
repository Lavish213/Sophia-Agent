# SOPHIA AGENT — AGENTS.md

## WHAT THIS IS
AI voice acquisitions agent for a real estate wholesaling business in
San Joaquin County, California. Sophia calls and receives calls from
distressed-property sellers, qualifies them, and books walkthroughs.
Ground-up rebuild of an earlier prototype (Lavish213/rei-agent) after
an audit found core paths silently broken. This repo is scoped to a
working MVP first: manual CSV lead import, comps/ARV/MAO calculation,
correctly-wired voice pipeline, and a dashboard. Automated lead
scraping, SMS drip sequences, and elaborate live emotional-state
tracking are deferred to a phase 2, once the core is proven on real
calls.

## OWNER
Angelo Washington. Goes by Alanzo Alcarez for the business.
Business name: San Joaquin House Buyers
Business domain: sanjoaquinhousebuyers.com

## STACK
- Backend: Python 3.11, FastAPI
- Voice: SignalWire SDK + Pipecat + Deepgram (STT + TTS) + Claude API
- Bob worker: standalone process, same repo, generates call briefs
- Database: Supabase (Postgres), RLS enabled on every table
- Dashboard: Next.js 14 (pinned), Tailwind, Supabase Auth + JS client
- Hosting: Railway (backend + bob worker), Vercel (dashboard)
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
- Always `import backend.lib.db as db` and call `db.fn(...)` —
  never `from backend.lib.db import fn`. A from-import binds the
  function at import time, which silently breaks test monkeypatching
  and makes call sites harder to trace back to db.py.
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
backend/api/                  → FastAPI route handlers
bob/                           → standalone call-brief worker process
dashboard/                     → Next.js app, Supabase Auth
scripts/                       → one-off scripts, never imported by backend
supabase/migrations/           → schema files only
tests/                         → pytest coverage for backend/*

## DATABASE TABLES
properties          → cached distressed properties (no phone numbers)
contacts             → skip-traced owner contact info
leads                → active pipeline leads, one per property
calls                → call records, transcripts, disposition
transcript_chunks    → per-utterance transcript rows for a call
call_events          → structured event log for a call
comps                → comparable sales entered per property
offers               → offer drafts/status tied to a lead
dnc_list             → numbers that must never be called/texted
lead_intel_packets   → structured facts extracted across calls
decision_records     → audit trail of bob's call-brief decisions
seller_memory        → durable per-lead facts read at call start

## BUILD ORDER
1. backend/lib/config.py + db.py     ← START HERE
2. supabase/migrations/0001_init.sql
3. backend/scout/parser.py + scorer.py
4. backend/comps/calculator.py
5. backend/compliance/compliance.py
6. backend/api/main.py + routes
7. backend/voice/webhook.py + agent.py + tools.py
8. bob/ worker
9. dashboard/ (Next.js)
10. Railway + Vercel deployment
