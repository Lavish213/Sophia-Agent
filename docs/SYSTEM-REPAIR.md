# Standalone voice safety repair

This is a separate fallback runtime, not a second agent silently running beside REI. Its schema, Bob fallback and shared tenant/brief integration remain distinct and incomplete.

Recovered changes: deterministic first-sentence AI disclosure before property details; signed SignalWire compatibility callbacks and a five-minute call-bound media token; server-selected lead/caller identity; future/timezone-aware booking; acknowledged booking/callback database writes; synchronous tool I/O moved off the audio event loop; internal MAO excluded from spoken quote authority; verified-only source/recording/callback claims; deterministic voice STOP interception and phone-wide suppression SQL; opt-out precedence over post-call classification.

Configure `SIGNALWIRE_SIGNING_KEY` (provider signing key, not API token) and the exact public HTTPS `PUBLIC_URL`. Apply `supabase/migrations/0011_voice_suppression.sql` before using suppression. Missing authentication configuration fails closed. Failed suppression ends the sales conversation without claiming removal; durable outage recovery remains open. The compatibility form signature follows SignalWire Scheme B. Provider replay prevention and single-use stream leases remain production gates.

Recovered full unit suite: 450 tests pass. Test configuration forces dummy loopback Supabase settings and denies unmocked database clients. Older route unit fixtures explicitly override authentication; new authentication tests use an independent application without the override. This is not proof of real recognition, interruption behavior, provider delivery, calendar reservations, or deployed database permissions.

Remaining: operator membership/RLS; attributable seller confirmations and bound Bob brief contract; approved voice quote workflow; atomic availability reservation, cancellation/rescheduling and calendar delivery; durable suppression recovery; dependency reproducibility; full baseline/upgrade migrations; real audio/accessibility/duplex latency and provider recovery. Nothing deployed or called. No A grade or human-equivalence claim.
