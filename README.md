# Sophia Agent

AI voice acquisitions agent for San Joaquin House Buyers. Sophia calls and
receives calls from distressed-property sellers, qualifies them, and books
walkthroughs — then the dialer and follow-up workers take it from there:
working an uploaded lead list, calling it, and following up by text and
email. Ground-up rebuild of an earlier prototype
([`Lavish213/rei-agent`](https://github.com/Lavish213/rei-agent)) after an
audit found several core paths silently broken — see `AGENTS.md` for the
project's hard rules and full scope.

## Stack

- Backend: Python 3.11, FastAPI, [Pipecat](https://pipecat.ai) 1.6+
- Voice: SignalWire (Twilio-protocol-compatible telephony) + Deepgram (STT & TTS) + Claude
- SMS: SignalWire. Email: SendGrid.
- Bob worker: a second process that generates call briefs ahead of time
- Dialer worker: a third process that works an uploaded lead list on its own
- Database: Supabase (Postgres), Row Level Security on every table
- Dashboard: Next.js 14 (pinned), Tailwind, Supabase Auth
- Hosting: Railway (backend + bob + dialer), Vercel (dashboard)

## One-time setup

### 1. Supabase

1. Create a new Supabase project.
2. Open the SQL Editor and run `supabase/migrations/0001_init.sql`, then
   `supabase/migrations/0002_outreach.sql`, in that order.
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

### 4. Backend environment

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
ruff check backend/ bob/ dialer/ tests/
```

### 5. Deploy the backend (Railway)

This repo runs three processes from the same codebase (`Procfile`):

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

Railway needs these as three separate services pointing at the same repo
(one per Procfile process type — `railway.json` configures the `web`
service; create two more services for `worker` and `dialer` with their
start commands set to `python -m bob.main` and `python -m dialer.main`
respectively). Set the full `.env` on all three services.

Once deployed, set `PUBLIC_URL` to the `web` service's Railway domain and
redeploy, then finish the SignalWire webhook setup from step 2.

### 6. Deploy the dashboard (Vercel)

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
4. When a call resolves — whether it connects and Sophia actually talks to
   someone, or it never connects at all (no-answer/busy/failed, reported by
   SignalWire's status callback) — `backend/alerts/followup.py` sends a
   disposition-appropriate SMS and, if an email is on file, an email too.
   HOT/WARM calls get a short confirmation/follow-up text; COLD/DEAD calls
   get nothing (no pressure); a no-answer gets a "sorry we missed you" text
   and email.
5. Every send re-checks opt-out status immediately before sending, not just
   at dial time. Replying STOP to a text sets `opted_out` and stops both
   future calls and texts for that lead; replying START clears it.

## Testing

```bash
pytest tests/ -q          # 140 tests: backend, bob, dialer
ruff check backend/ bob/ dialer/ tests/
cd dashboard && npm run lint && npm run build
```

Everything above runs and is verified without live provider credentials.
**Placing or receiving an actual phone call, text, or email requires real
SignalWire, Deepgram, Anthropic, and SendGrid credentials plus a working
`PUBLIC_URL`** — that path can only be exercised against a real deployment,
not in an offline sandbox.

## What's in this MVP vs. deferred

CSV lead import, comps/ARV/MAO calculation, the voice pipeline, batch
outbound calling with SMS/email follow-up, post-call intelligence
extraction, Bob's call-brief worker, and the dashboard are all live.
Automated lead-sourcing scrapers and the old repo's elaborate live
trust/resistance/emotional-state tracking are deferred to a phase 2, once
this core is proven on real calls.
