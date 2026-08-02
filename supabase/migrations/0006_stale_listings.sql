-- Listing state drives who may legally be contacted about a stale listing.
-- While a property is actively listed the seller is under an exclusive
-- agreement, so outreach goes to the listing agent. Once the listing is
-- expired, withdrawn, or cancelled the owner may be approached directly.
alter table properties add column if not exists listing_status text default 'unknown';
alter table properties add column if not exists listed_at date;
alter table properties add column if not exists listing_price bigint;
alter table properties add column if not exists listing_agent_name text;
alter table properties add column if not exists listing_agent_phone text;
alter table properties add column if not exists listing_source text;
alter table properties add column if not exists listing_checked_at timestamptz;

-- stale_listing_flagged_at stops the discovery worker re-creating a lead for
-- the same stale listing on every cycle
alter table properties add column if not exists stale_listing_flagged_at timestamptz;

create index if not exists idx_properties_stale_listings
  on properties (listing_status, days_on_market);
