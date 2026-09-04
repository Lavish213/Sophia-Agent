# Sophia Agent — Complete Project Reference

Everything about this system, end to end. Written to be the single document
you can hand someone — or come back to yourself in six months — and
understand the whole thing without reading the code.

**Repository:** https://github.com/Lavish213/Sophia-Agent

---

## 1. What this is

An AI voice acquisitions agent for **San Joaquin House Buyers**, a real
estate wholesaling business in San Joaquin County, California.

Sophia calls distressed-property sellers, qualifies them, books
walkthroughs, and follows up by text and email. She also answers inbound
calls and texts. Around her sits the machinery that finds leads in the
first place, decides who to call next, prices the deal, and sends it out to
cash buyers.

It is a ground-up rebuild of an earlier prototype
([`Lavish213/rei-agent`](https://github.com/Lavish213/rei-agent)) after an
audit found its core paths silently broken — CSV import crashed on every
row, outbound calling stopped after three leads and never recovered, the
offers table and the code disagreed on column names, and there was no row
level security anywhere.

### Quick facts

| | |
|---|---|
| Backend | ~5,900 lines of Python 3.11 |
| Tests | 426 backend + 10 dashboard |
| Migrations | 10 |
| Database tables | 18 |
| API routes | 30 |
| Dashboard pages | 13 |
| Deployed processes | 4 |
| Commits | 45 |

### The one thing to know

**Nothing here has ever run against a real phone call.** Every test mocks
the boundary. The logic is verified and the contracts are pinned, but
"passes 426 tests" and "works on the phone" are different claims and only
the first is proven. See §17.

---

## 2. Architecture

Four processes, all from the same repo, deployed separately on Railway.
They never call each other — **every handoff goes through the database.**

```
                          ┌──────────────────┐
                          │   SUPABASE DB    │
                          └────────┬─────────┘
        ┌──────────────┬───────────┼───────────┬──────────────┐
        │              │           │           │              │
    ┌───▼───┐    ┌─────▼─────┐ ┌───▼───┐  ┌────▼────┐   ┌─────▼─────┐
    │  web  │    │ discovery │ │  bob  │  │ dialer  │   │ dashboard │
    │       │    │           │ │       │  │         │   │ (Vercel)  │
    └───────┘    └───────────┘ └───────┘  └─────────┘   └───────────┘
   FastAPI +      finds leads   plans the   places the    what you
   Sophia's       + skip trace  next call   calls         look at
   live calls
```

| Process | Command | Cadence | Job |
|---|---|---|---|
| `web` | `uvicorn backend.api.main:app` | always on | REST API, SignalWire webhooks, Sophia's live call pipeline |
| `worker` | `python -m bob.main` | `BOB_WORKER_INTERVAL_MINUTES` (5) | writes each lead's call plan and queue priority |
| `dialer` | `python -m dialer.main` | `DIALER_INTERVAL_MINUTES` (10) | places outbound calls |
| `discovery` | `python -m discovery.main` | `REDDIT_POLL_INTERVAL_MINUTES` (30) | finds leads, skip traces, flags stale listings |

---

## 3. The complete lifecycle

```
  FIND ──► VALIDATE ──► ENRICH ──► PLAN ──► CALL ──► FOLLOW UP ──► PRICE ──► ASSIGN
   │           │           │         │        │          │           │          │
 6 sources  data      skip trace   Bob     Sophia    text/email    comps     buyers
           quality    (address              live      by outcome   → ARV     blast
                      → phone)              voice                  → MAO
                                              │
                                              ▼
                                        post-call intel
                                     (Claude reads transcript)
                                              │
                                              └──► back to PLAN, smarter
```

That last arrow is the learning loop. It was broken in **four** separate
places and is the single most-repaired part of the system (§18).

---

## 4. Lead sources

Every lead, from every source, is created through one function:
`backend/scout/intake.py::intake_lead`. It normalizes phone numbers to
E.164, dedupes against existing leads, and scores the source.

| Source | Module | Gives a phone? | Automatic? |
|---|---|---|---|
| **Website form** | `api/routes/intake.py` | yes — seller types it | yes |
| **Inbound call** | `voice/context.py` | yes — caller ID | yes |
| **Inbound text** | `alerts/sms.py` | yes | yes |
| **CSV upload** | `scout/ingest.py` | if the list has one | yes |
| **Stale listings** | `scout/stale_listings.py` | from the list | yes |
| **Reddit** | `scout/reddit.py` | **no** | needs manual conversion |
| *Skip trace* | `scout/skiptrace.py` | yes — *enrichment, not a source* | yes |

Inbound sources score highest (`web_form` 80, `inbound_call` 70,
`inbound_sms` 65) — someone who contacts you is worth more than someone you
found.

### Phone normalization matters

SignalWire reports E.164 (`+12094771234`); CSVs carry every other format.
Without normalization at intake, the same person becomes two leads and
their call history splits. Everything normalizes at the front door, and
`find_existing_lead` checks six format variants on lookup.

### Stale listings — the legal branch

A listing sitting 60–70+ days is a strong signal. But **who** you contact
depends on listing status, and this is a legal constraint rather than a
preference:

| Listing status | Contact |
|---|---|
| active, listed, for_sale, pending | the **listing agent** |
| expired, withdrawn, cancelled | the **owner**, directly |
| unknown | nobody — held for review |

While a property is actively listed the seller is under an exclusive
agreement. Approaching them directly can be **intentional interference with
contract** under California law, with punitive damages available. An active
listing with no agent phone on file is *skipped*, never quietly fallen back
to the owner.

### Deliberately not built

- **Zillow / Redfin / Realtor.com scraping** — all three forbid it and
  enforce it. `days_on_market` is obtainable legitimately from an MLS feed
  or a CSV export.
- **California eviction records** — CCP §1161.2 masks unlawful detainer
  filings for 60 days and only unseals them if the landlord won at trial.
  The old repo had a scraper chasing data that mostly does not exist.
- **Court portal scraping** — captcha-gated, breaks silently.

Full research, costs, and rejected sources: [`docs/LEAD_SOURCES.md`](docs/LEAD_SOURCES.md).

---

## 5. Data validation

`backend/scout/validate.py`. List data is dirty; nothing checked it before.

| Caught | Example |
|---|---|
| Fake phone | `209-555-0100` |
| Invalid area code | starts 0 or 1 |
| Service codes | 911, 411 |
| Repeated / sequential | `2222222222`, `123-456-7890` |
| **Owner is an entity** | "Acme Holdings **LLC**", "Family **Trust**" |
| Placeholder name | "OWNER", "Current Resident", "N/A" |
| PO box | you cannot buy a PO box |
| No street number | "Main Street, Stockton" |
| Impossible year built | 2099, or 1200 |
| Contradictory specs | 4 beds in 400 sqft |
| Duplicates | same APN or address twice in one file |

**Only a missing address rejects a row.** A bad phone drops *the phone* and
keeps *the property* — the house is real and skip trace can find a working
number. Discarding the record over one bad column loses the lead you paid
for.

The entity check matters most in practice: much of a bad list is LLCs and
trusts, and you cannot have a conversation with an LLC.

Each property stores `data_issues` and `data_confidence`.

---

## 6. Sophia — the voice agent

`backend/voice/`. Pipecat 1.6 pipeline: SignalWire transport → Deepgram STT
→ Claude → Deepgram TTS.

### What she knows before speaking

1. **Caller name** and first name
2. **Relationship** — brand-new stranger / returning your voicemail /
   outbound attempt N / previously opted out
3. **Property** — address, distress type, ARV, offer range, prior-call facts
4. **Bob's plan** — objective, what to find out, tone, opener, what to avoid

Without #2 she greets a stranger like an old contact, which is the most
obvious tell that a bot is calling.

### Her tools

| Tool | Does |
|---|---|
| `get_offer_range` | quotes a range — only from real comps |
| `book_appointment` | books the walkthrough, alerts the owner |
| `send_details` | **texts or emails the seller mid-call** |
| `request_owner_callback` | flags for a human, texts the owner |
| `end_call` | ends cleanly with a disposition |

### The prompt

`backend/voice/prompts/sophia_runtime.md`. Key rules:

- **Never make things up.** Only state facts from the call context. Never
  invent a square footage or quote a firm price. "I don't have that in
  front of me" beats guessing.
- **Never deny being AI.** Per the FCC's Feb 2024 ruling, AI voices in
  automated calls fall under TCPA with caller-identification requirements.
  Dodging is a compliance problem, not just a trust one.
- **Never promise to send something without sending it in the same turn.**
- **An objection bank** for the calls that actually happen: "where did you
  get my number", "are you a robot", "take me off your list", "are you a
  realtor", "how much will you give me", "I'm busy".
- **Fair housing** — never engage with protected characteristics.

### Voicemail

Every outbound call runs answering-machine detection
(`machine_detection="DetectMessageEnd"`), so the answer webhook is delayed
until the greeting finishes and arrives with `AnsweredBy`:

| AnsweredBy | Result |
|---|---|
| `human` (or absent) | live pipeline |
| `machine_end_*` | spoken voicemail, then hang up |
| `machine_start` | hang up — greeting isn't done, message would be cut off |
| `fax`, `unknown` | hang up |

Scripts vary by attempt and stop after `MAX_VOICEMAILS_PER_LEAD` (3). The
callback number is spoken digit by digit.

### Turn-taking

Uses Pipecat's trained **smart turn model** rather than a fixed silence
timer, with VAD at 0.6s (Pipecat's 0.2s default cuts sellers off
mid-sentence). Research puts the natural response window at 500–1,200 ms;
past 800 ms callers consciously notice. Falls back to the timeout strategy
if the model can't load.

### Post-call

Claude reads the transcript via a **forced tool call** (not free-text JSON
parsing) and extracts disposition, motivation, timeline, price floor,
objections, occupancy, condition, summary, and next action — written back
to the lead.

---

## 7. Follow-up

`backend/alerts/followup.py`. Fires on every call outcome:

| Outcome | Seller gets | You get |
|---|---|---|
| **HOT** | confirmation text | **SMS alert** |
| **WARM** | confirmation text | — |
| **Voicemail** | "just left you a voicemail" text | — |
| **No answer / busy / failed** | text **and** email | — |
| **COLD / DEAD** | nothing — no pressure | — |
| **Appointment booked** | text with the actual day and time | **SMS alert** |
| **Escalation** | — | **SMS alert** |

Every send re-checks opt-out immediately before sending. Follow-ups are
guarded against duplicate delivery — SignalWire can redeliver a status
callback, and a conditional DB update ensures one send.

### Text style

Short (142–166 chars), ends with a **question**, uses the seller's first
name and real address. The opt-out footer stays on every message **until
the seller texts back** — once they reply it is a conversation, not a
campaign, and a compliance footer on every reply is the clearest tell
nobody is really there.

---

## 8. Bob — the call planner

`bob/`. Never talks to anyone, never finds a lead. Takes leads that exist
and writes Sophia's game plan.

### The checkbox ladder

Walks a fixed priority order and stops at the first unknown:

```
right person → property confirmed → occupancy → condition
             → timeline → motivation → next step
```

If you've never spoken to them, the whole call is "confirm I'm talking to
the owner." That's what stops Sophia cramming seven questions into one call
and sounding like a survey.

### The brief

| Field | Example |
|---|---|
| `missing_box` | `condition` |
| `phase` | `LIGHT_DISCOVERY` |
| `objective` | "learn what repairs or issues the property has" |
| `mood` | `distressed` |
| `opener_hint` | "seller may be stressed — open light and stay calm" |
| `avoid` | pricing, legal advice, foreclosure guidance |
| `escalation_rules` | when to hand to a human |

Situation drives tone: pre-foreclosure → `distressed`; probate, inherited,
divorce → `guarded`; high motivation → `motivated`.

Briefs regenerate whenever the last call is newer than the brief, so what
Sophia learned on call one shapes call two.

### The prioritizer

`bob/prioritizer.py`. The dialer used to sort by distress score — what the
list provider thought before anyone spoke to the owner.

**Up:** asked for a callback · callback due · motivation from a real call ·
marked hot · urgent timeline · never tried · gone cold worth retrying

**Down:** 5+ failed attempts · voicemail cap hit · list data flagged
unreliable

Each lead carries its reasons, so a queue position can be explained.

**"Waiting on a human" is a tier, not a bonus.** Anyone who asked for a
callback outranks any cold lead however distressed the property. As a
bonus, a distress-90 lead still beat a person actively waiting — wrong at
any weighting.

---

## 9. Compliance

`backend/compliance/`. Fails closed everywhere — a check that errors blocks
the call.

### Calling hours are in the recipient's timezone

TCPA is based on the **called party's** local time. Absentee owners are a
primary wholesaling target and often keep an out-of-state number, so 8pm
Pacific is 11pm Eastern — a violation from code that reads as correct.

`backend/compliance/timezones.py` maps area code → timezone. Unknown area
codes require the time to be valid on **both coasts**, so an unmapped
number is dialed conservatively rather than assumed local.

### Every gate

- **Calls:** opted_out, dnc_blocked, calling hours (recipient tz), DNC list
  (both phones)
- **Texts:** the same five — texts carry identical TCPA time restrictions
- **STOP** from an unknown number → added to `dnc_list`, no lead created
- **Skip-traced numbers** scrubbed against DNC and TCPA-litigator lists
  before ever being written to a lead; the scrub **fails closed**
- **Marking a lead dead never touches consent** — resetting `opted_out`
  would silently re-enable outreach to someone who replied STOP

### Kill switch

Set `MAX_CONCURRENT_OUTBOUND=0` and restart the dialer. The capacity check
fails immediately and no calls are placed. Pinned by a test — the
comparison looks like an ordinary bounds check and would be easy to
"simplify" into one that treats zero as unlimited.

---

## 10. Pricing and disposition

**Comps → ARV → MAO.** Enter comparable sales per property; the calculator
does recency- and distance-weighted price-per-sqft. `MAO = (ARV × 0.70) −
$25,000`, both configurable. All money is integer cents throughout — never
floats.

**Buyers list.** `buyers` table with the criteria a deal is matched on:
price range, cities, beds, sqft, proof of funds. Matching ranks buyers
who've closed most first.

**Deal blast.** Sends a matched deal by SMS or email, reusing the existing
senders so it inherits opt-out handling. A uniqueness constraint on
`(property, buyer, channel)` means the same buyer is never sent one deal
twice however often you run it. Failed sends are recorded, not dropped.

**Contract fields** on offers: under-contract date, inspection deadline,
close date, assignment fee, assigned buyer.

---

## 11. Data model

18 tables. RLS enabled on all. Money in integer cents.

| Table | Holds |
|---|---|
| `properties` | distressed properties, distress score, ARV/MAO, data quality |
| `contacts` | skip-traced owner contact info |
| `leads` | the pipeline — one per property, all learned facts, priority |
| `calls` | call records, disposition, `answered_by`, `voicemail_left` |
| `transcript_chunks` | per-utterance transcript |
| `call_events` | structured event log per call |
| `comps` | comparable sales |
| `offers` | offers + contract tracking |
| `dnc_list` | never call or text |
| `sms_messages` | inbound + outbound SMS |
| `email_messages` | inbound + outbound email |
| `reddit_matches` | scored Reddit posts, pre-lead |
| `buyers` | cash buyers and their criteria |
| `deal_blasts` | which deal went to which buyer |
| `worker_runs` | worker heartbeats |
| `decision_records` | Bob's audit trail |
| `lead_intel_packets` | **read-only — nothing writes it** (§17) |
| `seller_memory` | **superseded — Bob reads the lead row instead** |

---

## 12. API

30 routes, all under `/api`.

**Voice:** `POST /voice/inbound` · `POST /voice/outbound/{lead_id}` ·
`POST /voice/status` · `WS /voice/stream`

**Intake:** `POST /intake/web-form` (secret-gated) · `POST /sms/inbound` ·
`POST /properties/upload`

**Leads:** `GET /leads` · `GET /leads/{id}` · `PATCH /leads/{id}` ·
`POST /leads/{id}/call`

**Pricing:** `GET|POST /properties/{id}/comps` ·
`POST /properties/{id}/comps/recalculate` · `GET|POST /leads/{id}/offers` ·
`PATCH /offers/{id}`

**Dispo:** `GET|POST /buyers` · `GET /properties/{id}/matching-buyers` ·
`POST /properties/{id}/blast` · `GET /properties/{id}/blasts`

**Discovery:** `GET /discovery/reddit-matches` ·
`POST /discovery/reddit-matches/{id}/convert` · `.../dismiss`

**Ops:** `GET /health` · `GET /workers/health`

---

## 13. Dashboard

Next.js 14 (pinned — the old repo's silent drift to Next 16 broke two
pages), Supabase Auth on every route except `/login`, `/sell`, and
`/api/lead`.

| Page | Shows |
|---|---|
| `/` | active leads, hot leads, **waiting on you**, recent calls |
| `/leads` | all leads + source + "no phone" flag |
| `/leads/[id]` | full detail, comps entry, ARV recalc, offers, texts, emails |
| `/calls` · `/calls/[id]` | calls, transcript, event timeline, AMD verdict |
| `/properties` | properties + CSV upload |
| `/buyers` | cash buyers + add form |
| `/discovered` | Reddit matches, convert or dismiss |
| `/reasoning` | **Bob's plans and his call queue with reasons** |
| `/health` | **worker heartbeats** — running / late / not running / erroring |
| `/settings` | provider health, **DNC list**, opted-out leads |
| `/sell` | **public** seller capture page |
| `/login` | operator sign-in |

`/sell` posts to a **server-side** route handler holding the intake secret,
so the secret never reaches the browser. Includes a honeypot field.

---

## 14. Configuration

48 settings, all in `backend/lib/config.py`, mirrored in `.env.example`.
`tests/test_env_example.py` fails if they drift. No bare `os.getenv`
anywhere else.

**Required (app won't boot):** `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`,
`ANTHROPIC_API_KEY`, `DEEPGRAM_API_KEY`

**Needed for calls:** `SIGNALWIRE_PROJECT_ID`, `SIGNALWIRE_TOKEN`,
`SIGNALWIRE_SPACE`, `SIGNALWIRE_PHONE`, `PUBLIC_URL`

**Optional:** `SENDGRID_API_KEY` + `FROM_EMAIL` (email), `REDDIT_*`
(discovery), `BATCHDATA_API_KEY` (skip trace), `INTAKE_WEBHOOK_SECRET` (web
form), `OWNER_PHONE` (your alerts)

**Safety dials:** `MAX_CONCURRENT_OUTBOUND` (0 = kill switch),
`MAX_VOICEMAILS_PER_LEAD`, `CALLING_HOURS_START/END`,
`OUTBOUND_REATTEMPT_HOURS`, `INTAKE_AUTO_CALL`

---

## 15. Deployment

1. **Run all 10 migrations** in numeric order — skipping one produces
   missing-column errors at runtime, not at deploy
2. **Create the operator account** in Supabase Auth (no self-serve signup)
3. **Deploy 4 Railway services** from this repo, full env on each
4. **Set `PUBLIC_URL`** to the web service's real domain, redeploy —
   chicken-and-egg, you can't know it until step 3
5. **Point SignalWire's webhooks** at `/api/voice/inbound` and
   `/api/sms/inbound`
6. **Deploy the dashboard** to Vercel

**Deploy the dialer with `MAX_CONCURRENT_OUTBOUND=0`.** It starts calling
real people the moment it comes up with leads in the database.

### First-call order

1. **Call your own number** — inbound exercises the stream, transport, and
   prompt with zero risk to a stranger
2. **One outbound to yourself, let it hit voicemail** — tests machine
   detection, the voicemail script, and the follow-up text in one pass
3. **Then** set `MAX_CONCURRENT_OUTBOUND=1` and watch a few real calls
4. **Then** turn it up

Watch: latency (metrics on, target p95 < 800 ms) and
`MACHINE_DETECTION_TIMEOUT_SECONDS` (30 — most likely to need tuning).

---

## 16. Testing

```bash
pytest tests/ -q
ruff check backend/ bob/ dialer/ discovery/ tests/
cd dashboard && npm test && npm run lint && npm run build
```

426 backend tests across 42 files, 10 dashboard tests.

Two suites deserve mention:

- **`test_voice_call_flow.py`** drives the real webhooks with the form
  payloads SignalWire posts and **parses the response as XML** — malformed
  LaML makes SignalWire drop a call with no useful error.
- **`test_voice_pipeline_assembly.py`** constructs the real Deepgram,
  Anthropic, and Pipecat objects with throwaway keys. No network calls — it
  exists to catch Pipecat API drift on upgrade, which otherwise surfaces
  mid-call.

---

## 17. Known gaps

### Not built

- **Purchase contract generation.** Nothing produces one. Needs a CA
  contract an attorney approves, not something invented.
- **Title/escrow coordination.** Manual.
- **Licensed property data.** The machinery is built and idle. PropStream
  or similar (~$500/mo) is what turns this into volume.
- **The buyers list has no rows.** The feature is real; the asset isn't.
  It's the most valuable thing in the business and the one thing that can't
  be built for you.

### Built but inert

- **`lead_intel_packets`** — `save_intel_packet` has no callers, so five
  Bob consumers (avoidances, escalation rules, mood, confidence, source)
  degrade to defaults. All fall back to real property data now, so nothing
  is broken; the enrichment layer was simply never built.
- **`competitor_mentions`, `initial_trust_score`, `followup_urgency`,
  `PHASE_TO_STAGE`** — read or declared, never written. Harmless.

### Unverified

**No live call has ever been placed.** Also unverified: audio quality, real
STT accuracy on local accents, interruption handling in practice, whether
SignalWire's AMD timing suits this market, whether Sophia *sounds* right,
and BatchData's actual response shape (their docs are behind auth; the
extractor is written defensively against several plausible shapes).

---

## 18. Bug history

Worth reading — the failures clustered in one shape, and knowing it is the
fastest way to find the next one.

**Every significant bug was at a seam: something wrote, nothing read.** The
write side always looked correct in isolation and always passed its own
tests.

| Bug | Effect |
|---|---|
| Follow-up only fired if `end_call` was invoked | Sellers who hung up got no follow-up at all |
| Unknown inbound caller created no lead | Cold callers silently dropped |
| Unknown inbound texter created no lead | Same |
| Bob's brief never reached Sophia | An entire worker doing unused work |
| Bob's brief never regenerated | Call two used the plan from before call one |
| Bob's memory table never written | Bob's view of every seller permanently blank |
| Bob's field names didn't match | Ladder stuck on "condition" forever |
| Occupancy/condition never extracted | Two ladder rungs unsatisfiable |
| Escalations set a flag nobody read | "I want a human" reached no human |
| Owner HOT alert never built | `OWNER_PHONE` configured, read by nothing |
| Marking dead reset `opted_out` | Would re-enable outreach after STOP |
| Creative finance blocked on every lead | Whitelist read an always-empty packet |
| SMS skipped hours + DNC checks | Textable at 3am, and to DNC numbers |
| Calling hours in *our* timezone | 8pm Pacific = 11pm Eastern violation |
| Unbounded outbound query | High-distress leads never dialed at scale |
| CSV phones unnormalized | Same person became two leads |
| Comps/offers had no UI | ARV unusable — nothing could enter a comp |
| README listed 3 of 10 migrations | Would produce a broken deploy |

**The audit that keeps working:** list every field written, grep for who
reads it, investigate every zero.

---

## 19. Hard rules

From `AGENTS.md` — these are load-bearing:

- **No comments in Python.** SQL migrations may use `--`.
- **SignalWire only, never Twilio.** (The `signalwire` package wraps
  `twilio` internally; that's their official SDK and fine.)
- **All Supabase access through `backend/lib/db.py`.** No other module
  creates a client.
- **`from backend.lib import db` then `db.fn()`** — never
  `from backend.lib.db import fn`. Bare imports bind at import time and
  silently break test monkeypatching.
- **Never commit `.env`**, even with placeholders.
- **All money as integer cents.** ARV and MAO always integers.
- **Every env var declared in `config.py` and mirrored in `.env.example`.**
- **No business logic in API routes.**
- **loguru, never `print()`.**

---

## 20. Where to start reading

| Question | File |
|---|---|
| How does a lead get created? | `backend/scout/intake.py` |
| What does Sophia actually say? | `backend/voice/prompts/sophia_runtime.md` |
| How does a call work? | `backend/voice/webhook.py` → `agent.py` |
| How is the next call planned? | `bob/brief_generator.py` |
| Who gets called first? | `bob/prioritizer.py` |
| What stops an illegal call? | `backend/compliance/compliance.py` |
| Every database query | `backend/lib/db.py` |
| Every setting | `backend/lib/config.py` |
| Why a lead source was rejected | `docs/LEAD_SOURCES.md` |
