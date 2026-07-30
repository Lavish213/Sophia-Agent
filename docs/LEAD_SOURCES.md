# Lead sources — what works, what doesn't, and why

Research notes behind Sophia's lead sourcing. Written so nobody has to
re-derive this later, and so the honest limits stay visible.

## The one thing that matters

Sophia is a **voice** agent. A lead she can't call is not a lead.

Almost every "find motivated sellers" data source gives you a **property
address and an owner name** — not a phone number. Turning that into a
callable lead requires **skip tracing**, which is a paid, licensed service.
This is the single biggest constraint on lead sourcing, and it's the thing
most "just scrape it" plans miss.

So every source below is graded on two axes: can it find distress, and can
it produce a phone number.

## How the established players actually do it

Worth knowing, because it sets realistic expectations:

- **PropStream / BatchLeads** — license bulk county and public-record data
  rather than scraping it. PropStream acquired BatchLeads in July 2025, so
  the space is consolidating. Core lists are absentee owners, pre-foreclosure,
  tax delinquent, probate, and vacant. Property search starts around
  **$500/mo for 20k records**.
- **BatchData** — the API layer under that ecosystem. Skip tracing starts
  around **$2,000/mo for 100k records**, quoted at ~76% right-party contact
  accuracy.
- **DealMachine** — driving for dollars; a human photographs a distressed
  house and the app skip traces the owner.
- **Carrot** — SEO/PPC landing pages with two-step opt-in forms. These are
  **inbound** leads: the seller submits their own phone number, so there's no
  skip-trace cost and no consent ambiguity.

The pattern: nobody's competitive advantage is scraping. It's licensed data
plus inbound marketing. Sophia should lean the same way.

## Source-by-source

### Built and working

| Source | Finds distress | Gives a phone | Notes |
|---|---|---|---|
| **CSV import** | via list provider | yes, if the list has it | Propwire-format. You control the list. |
| **Web form** | highest intent | **yes, seller-provided** | Best leads in the system. Express consent. |
| **Inbound call** | highest intent | **yes, caller ID** | Was silently dropping leads; now fixed. |
| **Inbound SMS** | high intent | **yes** | Was silently dropping leads; now fixed. |
| **Reddit** | yes, weak signal | **no** | Public API, compliant. Needs manual contact-finding. |
| **Skip trace (BatchData)** | n/a — enrichment | **yes** | Turns address-only leads callable. Needs paid key. |

Inbound sources are ranked highest in `SOURCE_DEFAULT_SCORES` on purpose:
someone who contacts you is worth more than someone you found.

### Deferred — real, but needs money or access

- **Licensed property data (PropStream/BatchData property search).** The
  correct way to get pre-foreclosure, tax-delinquent, probate, and absentee
  lists. Costs real money. Recommended next investment once inbound is
  proven — the `skiptrace.py` adapter already speaks BatchData, so the
  property-search side is a small addition.
- **County tax-delinquent auction list.** San Joaquin publishes an auction
  list as a public PDF. Legitimately public, but it's an annual/periodic
  dump, not a live feed, and it needs PDF parsing plus APN→address
  resolution. Genuinely doable; low volume.
- **MLS expired / price-reduced (CRMLS RESO API).** Legitimate and
  high-quality, but requires an MLS membership and API credentials. Build
  the adapter when you have the license, not before.

### Rejected — and why

- **Eviction / unlawful detainer filings. Do not build this.** California
  **CCP §1161.2** masks UD records from public access for 60 days after
  filing, and they only *ever* become public if the landlord wins at trial
  within that window. A tenant who prevails keeps the record sealed
  permanently. The old repo had an `eviction_scraper.py` targeting exactly
  this. Scraping it is both largely futile and legally hazardous — and the
  people on those lists are tenants, not owners, so they can't sell you the
  house anyway.
- **Zillow / Facebook Marketplace scraping.** Straightforward ToS
  violations with active anti-bot enforcement. Gets you blocked, and worse.
- **Craigslist FSBO scraping.** Craigslist is historically aggressive about
  scraping, including litigation. The signal is thin and the risk is
  asymmetric.
- **Court probate/divorce scraping.** The old `court_scraper.py` targeted
  sjcourts.org. Court portals are usually captcha-gated and change
  frequently; screen-scraping them produces a fragile pipeline that breaks
  silently. Probate lists are better bought.

## Compliance rules that constrain all of this

- **TCPA** — calling hours are enforced in `backend/compliance/`. Every dial
  re-checks per lead.
- **DNC** — skip-traced numbers are scrubbed against DNC and TCPA-litigator
  lists *before* being written onto a lead. The scrub **fails closed**: if
  the check errors, the number is treated as blocked rather than dialed.
- **Consent** — web-form and inbound leads carry express consent. Purchased
  and skip-traced lists do not; those are cold outreach and carry more risk.
- **STOP** from an unknown number adds it to `dnc_list` instead of creating
  a lead.

## What this means practically

Ranked by return on effort:

1. **Put up a Carrot-style page and point the form at
   `POST /api/intake/web-form`.** Best leads, seller-provided phone numbers,
   clean consent, no per-record cost.
2. **Make sure inbound call and SMS are wired to the SignalWire webhooks.**
   These are now captured instead of dropped. Free.
3. **Buy a list** (PropStream or similar), export CSV, drop it in.
4. **Add a BatchData key** once you have address-only leads worth enriching.
5. Reddit runs in the background and costs nothing, but treat it as a trickle
   that needs manual work, not a pipeline.

## Verification status

Everything above is implemented and unit-tested except where noted. The
**live** behavior of the BatchData endpoints could not be verified from the
build sandbox — outbound access to non-allowlisted hosts is blocked by the
environment's network policy, and BatchData's docs are behind auth. The
adapter was written defensively against several plausible response shapes and
is covered by tests for each, but the first real call with a live API key
should be watched. The response-shape handling in `extract_contacts()` is the
part most likely to need a small adjustment.
