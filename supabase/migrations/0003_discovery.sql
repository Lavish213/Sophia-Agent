-- Automated lead discovery: Reddit seller-intent monitoring.
-- A match is NOT a lead by itself -- it has no phone number or address yet.
-- It becomes a real lead (and enters the normal call/text/email pipeline)
-- only once an operator converts it by supplying contact info.

create table reddit_matches (
  id uuid primary key default gen_random_uuid(),
  reddit_id text unique not null,
  subreddit text not null,
  title text not null,
  body text,
  url text not null,
  author text,
  created_utc bigint,
  post_score int,
  intent_score int default 0,
  intent_label text default 'none',
  status text default 'new',
  lead_id uuid references leads(id) on delete set null,
  created_at timestamptz default now()
);

create index idx_reddit_matches_intent_score on reddit_matches(intent_score desc);
create index idx_reddit_matches_status on reddit_matches(status);
create index idx_reddit_matches_subreddit on reddit_matches(subreddit);

alter table reddit_matches enable row level security;
create policy reddit_matches_service_role on reddit_matches for all using (auth.role() = 'service_role');
create policy reddit_matches_authenticated_all on reddit_matches for all using (auth.role() = 'authenticated');
