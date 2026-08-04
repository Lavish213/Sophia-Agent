# Sophia Agent

AI voice acquisitions agent for San Joaquin House Buyers. Sophia calls and
receives calls from distressed-property sellers, qualifies them, and books
walkthroughs — then the dialer and follow-up workers take it from there:
working an uploaded lead list, calling it, and following up by text and
email. A discovery worker finds sellers on its own by monitoring Reddit
for seller-intent posts. Ground-up rebuild of an earlier prototype
([`Lavish213/rei-agent`](https://github.com/Lavish213/rei-agent)) after an
audit found several core paths silently broken — see `AGENTS.md` for the
project's hard rules and full scope.

## Stack

- Backend: Python 3.11, FastAPI, [Pipecat](https://pipecat.ai) 1.6+
- Voice: SignalWire (Twilio-protocol-compatible telephony) + Deepgram (STT & TTS) + Claude
- SMS: SignalWire. Email: SendGrid.
- Bob worker: a second process that generates call briefs ahead of time
- Dialer worker: a third process that works an uploaded lead list on its own
- Discovery worker: a fourth process that finds sellers on Reddit on its own
- Database: Supabase (Postgres), Row Level Security on every table
- Dashboard: Next.js 14 (pinned), Tailwind, Supabase Auth
- Hosting: Railway (backend + bob + dialer + discovery), Vercel (dashboard)

## One-time setup

### 1. Supabase

1. Create a new Supabase project.
2. Open the SQL Editor and run **every** file in `supabase/migrations/` in
   numeric order, 0001 through 0010. Later migrations add columns the code
   expects — skipping one produces "column does not exist" errors at
   runtime rather than at deploy, so it is worth checking the highest
   number in that directory against the last one you ran.
3. Under Authentication → Users, create the one operator account (email +
   password) that will sign into the dashboard. This is a single-operator
   tool — there's no self-serve signup.
4. Grab the project URL, the `service_role` key (backend), and the `anon`
   key (dashboard) from Project Settings → API.

### 2. SignalWire

1. Create a SignalWire space and buy a phone number.
2. Note the Project ID, API Token, and Space URL (e.g. `example.signalwire.com`).
3. Once the backend is deployed (step 5) and you have its public URL, set
   the phone number's voice webhook ("a call comes in") to
   `https://<your-backend-domain>/api/voice/inbound` (HTTP POST), and its
   messaging webhook ("a message comes in") to
   `https://<your-backend-domain>/api/sms/inbound` (HTTP POST) — the second
   one is what makes STOP/START opt-out actually work.

### 3. SendGrid

Create a SendGrid account, verify a sending domain or single sender address,
and generate an API key. That address becomes `FROM_EMAIL`.

### 4. Reddit (optional — powers automatic lead discovery)

1. Create a Reddit account (or use an existing one) and register an app at
   https://www.reddit.com/prefs/apps — choose type "script".
2. Note the client ID (under the app name) and client secret.
3. Set `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, and `REDDIT_USER_AGENT`
   (a descriptive string, e.g. `sophia-agent:v1 (by u/yourusername)`) in
   `.env`. Without these, the discovery worker runs as a no-op — nothing
   breaks, it just never finds anything.

### 5. Backend environment

Copy `.env.example` to `.env` and fill in every value — `SUPABASE_URL`,
`SUPABASE_SERVICE_KEY`, `ANTHROPIC_API_KEY`, `DEEPGRAM_API_KEY`,
`SIGNALWIRE_PROJECT_ID`, `SIGNALWIRE_TOKEN`, `SIGNALWIRE_SPACE`,
`SIGNALWIRE_PHONE`, `SENDGRID_API_KEY`, `FROM_EMAIL`, and `PUBLIC_URL` (your
backend's public HTTPS URL — used to build the `wss://` media stream URL
SignalWire connects to, and the status-callback/webhook URLs). Every
variable the code reads lives in `backend/lib/config.py`; `.env.example` is
kept in sync with it and `tests/test_env_example.py` fails if they drift.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pytest tests/ -q
ruff check backend/ bob/ dialer/ discovery/ tests/
```

### 6. Deploy the backend (Railway)

This repo runs four processes from the same codebase (`Procfile`):

- `web` — the FastAPI app (`uvicorn backend.api.main:app`), handles the REST
  API, the SignalWire voice/SMS webhooks, and the media websocket.
- `worker` — the Bob call-brief generator (`python -m bob.main`), polls
  Supabase every `BOB_WORKER_INTERVAL_MINUTES` and pre-computes a call brief
  for any lead that doesn't have one yet.
- `dialer` — the batch outbound dialer (`python -m dialer.main`), polls
  every `DIALER_INTERVAL_MINUTES` for leads due for a call attempt and
  places them, one at a time, up to `MAX_CONCURRENT_OUTBOUND` calls in
  flight at once (tracked in the database, not in memory, so it survives a
  restart and can't leak — see "Outbound calling" below).
- `discovery` — the Reddit lead-discovery worker (`python -m discovery.main`),
  polls every `REDDIT_POLL_INTERVAL_MINUTES` for new seller-intent posts and
  stores them as `reddit_matches` for manual review (see "Lead discovery"
  below).

Railway needs these as four separate services pointing at the same repo
(one per Procfile process type — `railway.json` configures the `web`
service; create three more services for `worker`, `dialer`, and `discovery`
with their start commands set to `python -m bob.main`,
`python -m dialer.main`, and `python -m discovery.main` respectively). Set
the full `.env` on all four services.

Once deployed, set `PUBLIC_URL` to the `web` service's Railway domain and
redeploy, then finish the SignalWire webhook setup from step 2.

### 7. Deploy the dashboard (Vercel)

```bash
cd dashboard
npm install
npm run build   # verify locally first
```

Deploy `dashboard/` to Vercel with these env vars set:

- `NEXT_PUBLIC_SUPABASE_URL` — same Supabase project URL as the backend
- `NEXT_PUBLIC_SUPABASE_ANON_KEY` — the `anon` key, **not** the service key
- `NEXT_PUBLIC_API_URL` — the backend's public URL (from step 5)

Sign in at `/login` with the operator account created in step 1.

## Outbound calling, texting, and email — how it actually works

Uploading a CSV only ingests it (scores, dedupes, creates leads) — it does
**not** call, text, or email anyone by itself. The `dialer` worker is what
picks leads up from there, on its own schedule:

1. Every `DIALER_INTERVAL_MINUTES`, it pulls up to `DIALER_BATCH_SIZE` leads
   that are due (not opted out, not DNC-blocked, not `closed`/`dead`, and
   either never called or last called more than `OUTBOUND_REATTEMPT_HOURS`
   ago).
2. Before every single dial it checks the number of calls currently in
   flight (`ended_at IS NULL` in the database) against
   `MAX_CONCURRENT_OUTBOUND`, and stops the cycle the moment it's at
   capacity — this is the exact thing that broke in the old repo, where an
   in-memory counter leaked and silently stopped all outbound calling after
   3 leads, forever, until a restart.
3. Each dial re-checks compliance (calling hours, opted-out, DNC) for that
   specific lead right before placing the call.
4. Every outbound call runs **answering-machine detection**. If a human
   picks up, the call connects to Sophia's live pipeline. If it reaches
   voicemail, she leaves a spoken message instead — the script is shorter
   and less repetitive on the second and third attempt, and she stops
   leaving them after `MAX_VOICEMAILS_PER_LEAD`. Fax and undetectable
   answers hang up without burning a message.
5. When a call resolves — whether it connects and Sophia actually talks to
   someone, reaches voicemail, or never connects at all
   (no-answer/busy/failed, reported by SignalWire's status callback) —
   `backend/alerts/followup.py` sends a disposition-appropriate SMS and, if
   an email is on file, an email too. HOT/WARM calls get a short
   confirmation/follow-up text; a voicemail gets a "just left you a
   voicemail" text; COLD/DEAD calls get nothing (no pressure); a no-answer
   gets a "sorry we missed you" text and email. Follow-ups are guarded
   against duplicate sends if SignalWire redelivers a status callback.
6. Every send re-checks opt-out status immediately before sending, not just
   at dial time. Replying STOP to a text sets `opted_out` and stops both
   future calls and texts for that lead; replying START clears it.

## Where leads come from

Every lead, whatever the source, is created through one function
(`backend/scout/intake.py`), which normalizes phone numbers to E.164 and
dedupes against existing leads before creating anything.

| Source | How it arrives | Gives a phone number? |
|---|---|---|
| **Website form** | `POST /api/intake/web-form` | Yes — seller types it in |
| **Inbound call** | Someone calls your SignalWire number | Yes — caller ID |
| **Inbound text** | Someone texts your SignalWire number | Yes |
| **CSV upload** | Dashboard → Properties | If your list has one |
| **Reddit** | Discovery worker, needs manual follow-up | No |
| **Skip trace** | Enrichment of address-only leads | Yes, if BatchData is configured |

Inbound sources score highest — someone who contacts you is worth more than
someone you found. A `STOP` text from an unknown number is added to the DNC
list instead of becoming a lead.

**Read [`docs/LEAD_SOURCES.md`](docs/LEAD_SOURCES.md)** for the full research:
what the established players (PropStream, BatchLeads, DealMachine, Carrot)
actually do, what each source costs, and which sources were deliberately
rejected and why — including why scraping California eviction filings is a
legal dead end.

### Website form setup

A working public capture page ships with the dashboard at **`/sell`** — it's
outside the login wall, and it posts to a server-side route (`/api/lead`)
that holds the shared secret and forwards to the backend. The secret is set
as `INTAKE_WEBHOOK_SECRET` in the dashboard's environment **without** a
`NEXT_PUBLIC_` prefix, so it never reaches the browser. Point
`sanjoaquinhousebuyers.com` (or a subdomain) at that page and leads flow
straight into the pipeline.

To wire up a form on a site you host elsewhere instead, post to
`POST /api/intake/web-form` with an `X-Intake-Secret` header from that
site's **backend**, never from browser JavaScript. The endpoint refuses to
run at all if the secret isn't configured, since it can create leads that
get called.

Set `INTAKE_AUTO_CALL=true` to have Sophia call a web-form lead immediately
(speed-to-lead). It's off by default, and still passes through the normal
compliance checks.

### Skip tracing

Most distress data gives you an address, not a phone number, so a voice agent
can't use it directly. Set `BATCHDATA_API_KEY` and the discovery worker will
enrich address-only leads on each cycle: it looks up contacts, scrubs the
number against DNC and TCPA-litigator lists, and only then writes it to the
lead. The scrub **fails closed** — if the check errors, the number is treated
as blocked rather than dialed. Without the key, enrichment is a no-op.

## Lead discovery — how Sophia finds leads on her own

Besides working leads you drop in as a CSV, the `discovery` worker finds
new sellers by itself:

1. Every `REDDIT_POLL_INTERVAL_MINUTES`, it checks a fixed list of San
   Joaquin-area subreddits (Stockton, Lodi, SanJoaquin) plus general
   real-estate/landlord/foreclosure/divorce subreddits for new posts.
2. Each post is scored for seller intent by keyword (hot/warm/cold/none —
   e.g. "need to sell fast" + "foreclosure" scores hot); anything below the
   threshold is skipped.
3. New matches (deduped by Reddit post ID) are stored in `reddit_matches`
   and show up on the dashboard's **Discovered** page, newest/hottest first.
4. Reddit never exposes a phone number, so a discovered match is **not** a
   lead yet and nothing is called, texted, or emailed automatically off it.
   A human reviews the post, finds contact info (typically by replying to
   the poster), and clicks **Convert to lead** — that creates a real
   property/contact/lead record. From that point on it's indistinguishable
   from a CSV-imported lead and flows through the same dialer → call →
   follow-up pipeline described above.
5. Without `REDDIT_CLIENT_ID`/`REDDIT_CLIENT_SECRET` set, the worker is a
   safe no-op — it logs nothing found rather than erroring.

## Testing

```bash
pytest tests/ -q          # backend, bob, dialer, discovery
ruff check backend/ bob/ dialer/ discovery/ tests/
cd dashboard && npm test && npm run lint && npm run build
```

The dashboard's `npm test` covers the `/api/lead` route handler, which is
the one piece of dashboard code holding a secret — it asserts the secret is
forwarded to the backend but never appears in a response, that the honeypot
silently absorbs bots, and that upstream errors don't leak detail to the
browser.

### Testing the call flow without a phone

`tests/test_voice_call_flow.py` drives the real webhook endpoints with the
same form payloads SignalWire posts, and parses the returned LaML as XML. It
covers the branches that decide what actually happens on a call: a human
gets the live audio stream, a finished voicemail greeting gets a spoken
message then a hangup, a greeting still in progress hangs up rather than
talking over it, fax hangs up, and a capped lead gets nothing. Malformed
LaML makes SignalWire drop the call with no useful error, so these assert
the XML parses rather than just checking for substrings.

`tests/test_voice_pipeline_assembly.py` constructs the real Deepgram,
Anthropic, and Pipecat objects with throwaway API keys and assembles the
actual pipeline. It never makes a network call — the point is to catch
Pipecat API drift on upgrade, which otherwise only shows up mid-call.

### Stopping outbound calling in a hurry

Set `MAX_CONCURRENT_OUTBOUND=0` on the dialer service and restart it. The
capacity check fails immediately, so the worker places no calls at all
while still running and logging. This is the fastest way to stop outreach
without a redeploy or a code change, and there is a test pinning it.

### Your first real call

Everything above runs offline. Placing an actual call needs live
credentials, so when you have them:

1. Deploy, set `PUBLIC_URL` to the `web` service's real domain, and confirm
   `/api/health` reports `supabase: ok` and the providers as `configured`.
2. Point the SignalWire number's voice webhook at `/api/voice/inbound` and
   **call it yourself first.** Inbound is the safer test — it exercises the
   stream, the transport, and the prompt without dialing a stranger.
3. Then trigger one outbound call to your own phone from a lead row, and
   let it go to voicemail on purpose. That single call exercises machine
   detection, the voicemail script, and the follow-up text in one pass.
4. Watch `MACHINE_DETECTION_TIMEOUT_SECONDS` (default 30). It's the setting
   most likely to need tuning for your market — too low clips greetings,
   too high delays live answers.

Everything above runs and is verified without live provider credentials.
**Placing or receiving an actual phone call, text, or email requires real
SignalWire, Deepgram, Anthropic, and SendGrid credentials plus a working
`PUBLIC_URL`** — that path can only be exercised against a real deployment,
not in an offline sandbox. Reddit discovery requires real
`REDDIT_CLIENT_ID`/`REDDIT_CLIENT_SECRET` to find anything, but degrades
safely without them.

## What's in this MVP vs. deferred

CSV lead import, comps/ARV/MAO calculation, the voice pipeline, batch
outbound calling with SMS/email follow-up, post-call intelligence
extraction, Bob's call-brief worker, Reddit-based lead discovery, and the
dashboard are all live. Broader automated lead-sourcing scrapers (RSS,
court records, eviction filings, CRMLS, cash-buyer lists) and the old
repo's elaborate live trust/resistance/emotional-state tracking are
deferred to a phase 2, once this core is proven on real calls.
