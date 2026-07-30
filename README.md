# Sophia Agent

AI voice acquisitions agent for San Joaquin House Buyers. Sophia calls and
receives calls from distressed-property sellers, qualifies them, and books
walkthroughs. Ground-up rebuild of an earlier prototype
([`Lavish213/rei-agent`](https://github.com/Lavish213/rei-agent)) after an
audit found several core paths silently broken — see `AGENTS.md` for the
project's hard rules and what's in vs. deferred for this MVP.

## Stack

- Backend: Python 3.11, FastAPI, [Pipecat](https://pipecat.ai) 1.6+
- Voice: SignalWire (Twilio-protocol-compatible telephony) + Deepgram (STT & TTS) + Claude
- Bob worker: a second process that generates call briefs ahead of time
- Database: Supabase (Postgres), Row Level Security on every table
- Dashboard: Next.js 14 (pinned), Tailwind, Supabase Auth
- Hosting: Railway (backend + worker), Vercel (dashboard)

## One-time setup

### 1. Supabase

1. Create a new Supabase project.
2. Open the SQL Editor and run `supabase/migrations/0001_init.sql` in full.
3. Under Authentication → Users, create the one operator account (email +
   password) that will sign into the dashboard. This is a single-operator
   tool — there's no self-serve signup.
4. Grab the project URL, the `service_role` key (backend), and the `anon`
   key (dashboard) from Project Settings → API.

### 2. SignalWire

1. Create a SignalWire space and buy a phone number.
2. Note the Project ID, API Token, and Space URL (e.g. `example.signalwire.com`).
3. Once the backend is deployed (step 4) and you have its public URL, set
   the phone number's "a call comes in" webhook to
   `https://<your-backend-domain>/api/voice/inbound` (HTTP POST).

### 3. Backend environment

Copy `.env.example` to `.env` and fill in every value — `SUPABASE_URL`,
`SUPABASE_SERVICE_KEY`, `ANTHROPIC_API_KEY`, `DEEPGRAM_API_KEY`,
`SIGNALWIRE_PROJECT_ID`, `SIGNALWIRE_TOKEN`, `SIGNALWIRE_SPACE`,
`SIGNALWIRE_PHONE`, and `PUBLIC_URL` (your backend's public HTTPS URL — used
to build the `wss://` media stream URL SignalWire connects to). Every
variable the code reads lives in `backend/lib/config.py`; `.env.example` is
kept in sync with it and `tests/test_env_example.py` fails CI if they drift.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pytest tests/ -q
ruff check backend/ bob/ tests/
```

### 4. Deploy the backend (Railway)

This repo runs two processes from the same codebase (`Procfile`):

- `web` — the FastAPI app (`uvicorn backend.api.main:app`), handles the REST
  API and the SignalWire webhook/websocket.
- `worker` — the Bob call-brief generator (`python -m bob.main`), polls
  Supabase every `BOB_WORKER_INTERVAL_MINUTES` and pre-computes a call brief
  for any lead that doesn't have one yet.

Railway needs these as two separate services pointing at the same repo (one
per Procfile process type — `railway.json` configures the `web` service;
create a second service for `worker` with its start command set to
`python -m bob.main`). Set the full `.env` on both services.

Once deployed, set `PUBLIC_URL` to the `web` service's Railway domain and
redeploy, then finish the SignalWire webhook setup from step 2.

### 5. Deploy the dashboard (Vercel)

```bash
cd dashboard
npm install
npm run build   # verify locally first
```

Deploy `dashboard/` to Vercel with these env vars set:

- `NEXT_PUBLIC_SUPABASE_URL` — same Supabase project URL as the backend
- `NEXT_PUBLIC_SUPABASE_ANON_KEY` — the `anon` key, **not** the service key
- `NEXT_PUBLIC_API_URL` — the backend's public URL (from step 4)

Sign in at `/login` with the operator account created in step 1.

## Testing

```bash
pytest tests/ -q          # 105 tests, backend + bob
ruff check backend/ bob/ tests/
cd dashboard && npm run lint && npm run build
```

Everything above runs and is verified without live provider credentials.
**Placing or receiving an actual phone call requires real SignalWire,
Deepgram, and Anthropic credentials plus a working `PUBLIC_URL`** — that
path can only be exercised against a real deployment, not in an offline
sandbox.

## What's in this MVP vs. deferred

See the "Scope" section this repo was built against for the full list —
in short: CSV lead import, comps/ARV/MAO calculation, the voice pipeline,
manual/on-demand outbound calling, post-call intelligence extraction, Bob's
call-brief worker, and the dashboard are all live. Automated lead-sourcing
scrapers, SMS drip sequences, and the old repo's elaborate live
trust/resistance/emotional-state tracking are deferred to a phase 2, once
this core is proven on real calls.
