-- The buyers list is the asset that makes a wholesale deal sellable. Without
-- it every contract needs a buyer found from scratch.
create table if not exists buyers (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  company text,
  phone text,
  email text,
  -- what they buy: cents, so a deal can be matched without unit confusion
  min_price bigint,
  max_price bigint,
  min_beds int,
  min_sqft int,
  -- cities they buy in, empty array means anywhere in the county
  cities text[] default '{}',
  property_types text[] default '{}',
  buys_cash boolean default true,
  proof_of_funds_on_file boolean default false,
  deals_closed int default 0,
  last_deal_at timestamptz,
  -- suppression mirrors the seller side so dispo blasts honour opt-outs
  opted_out boolean default false,
  email_opted_out boolean default false,
  active boolean default true,
  notes text,
  source text default 'manual',
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

-- One row per deal sent to one buyer, so response rate per buyer is knowable
-- and the same buyer is never blasted twice for the same property.
create table if not exists deal_blasts (
  id uuid primary key default gen_random_uuid(),
  property_id uuid references properties(id) on delete cascade,
  buyer_id uuid references buyers(id) on delete cascade,
  channel text default 'sms',
  status text default 'sent',
  responded boolean default false,
  responded_at timestamptz,
  created_at timestamptz default now(),
  unique (property_id, buyer_id, channel)
);

-- Contract tracking: an accepted offer is not a deal until it is under
-- contract, and the dates are what drive every deadline that follows.
alter table offers add column if not exists under_contract_at timestamptz;
alter table offers add column if not exists inspection_ends_at date;
alter table offers add column if not exists close_date date;
alter table offers add column if not exists assignment_fee bigint;
alter table offers add column if not exists assigned_buyer_id uuid references buyers(id) on delete set null;

create index if not exists idx_buyers_active on buyers (active, opted_out);
create index if not exists idx_deal_blasts_property on deal_blasts (property_id);
create index if not exists idx_offers_assigned_buyer on offers (assigned_buyer_id);

alter table buyers enable row level security;
alter table deal_blasts enable row level security;

create policy "service_role_all_buyers" on buyers for all to service_role using (true) with check (true);
create policy "authenticated_all_buyers" on buyers for all to authenticated using (true) with check (true);
create policy "service_role_all_deal_blasts" on deal_blasts for all to service_role using (true) with check (true);
create policy "authenticated_all_deal_blasts" on deal_blasts for all to authenticated using (true) with check (true);
