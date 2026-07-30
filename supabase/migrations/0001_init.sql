-- Sophia Agent base schema.
-- Every money-like value is bigint cents, never numeric/float.
-- RLS is enabled on every table: the backend and bob worker use the
-- service-role key (bypasses RLS by design), the dashboard uses an
-- authenticated Supabase Auth session gated by the policies below.

create extension if not exists "pgcrypto";

create table properties (
  id uuid primary key default gen_random_uuid(),
  apn text unique,
  address text not null,
  city text,
  state text default 'CA',
  zip text,
  county text default 'San Joaquin',
  owner_name text,
  beds int,
  baths numeric(3,1),
  sqft int,
  year_built int,
  lot_sqft int,
  distress_type text default 'unknown',
  equity_pct numeric(5,2),
  lien_amount bigint,
  tax_delinquent_amount bigint,
  nod_date date,
  auction_date date,
  last_sale_price bigint,
  estimated_value bigint,
  assessed_total_value bigint,
  zestimate bigint,
  vacant boolean default false,
  absentee_owner boolean default false,
  free_and_clear boolean default false,
  years_owned numeric,
  price_reduced boolean default false,
  days_on_market int,
  price_drop_count int,
  distress_score int default 0,
  deal_viable boolean default true,
  disqualified_reason text,
  motivation_score int,
  deal_score int,
  move_score int,
  estimated_arv bigint,
  mao bigint,
  arv_confidence text,
  comp_count int,
  price_per_sqft bigint,
  source text default 'csv_import',
  status text default 'new',
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

create index idx_properties_distress_score on properties(distress_score desc);
create index idx_properties_apn on properties(apn);

alter table properties enable row level security;
create policy properties_service_role on properties for all using (auth.role() = 'service_role');
create policy properties_authenticated_read on properties for select using (auth.role() = 'authenticated');

create table contacts (
  id uuid primary key default gen_random_uuid(),
  property_id uuid references properties(id) on delete cascade,
  name text,
  phone text,
  phone_2 text,
  email text,
  source text default 'csv_import',
  created_at timestamptz default now()
);

create index idx_contacts_property_id on contacts(property_id);
create index idx_contacts_phone on contacts(phone);

alter table contacts enable row level security;
create policy contacts_service_role on contacts for all using (auth.role() = 'service_role');
create policy contacts_authenticated_read on contacts for select using (auth.role() = 'authenticated');

create table leads (
  id uuid primary key default gen_random_uuid(),
  property_id uuid unique references properties(id) on delete cascade,
  stage text default 'new',
  owner_phone text,
  owner_phone_2 text,
  owner_email text,
  callable boolean default true,
  dnc_blocked boolean default false,
  opted_out boolean default false,
  call_attempts int default 0,
  last_called_at timestamptz,
  last_call_outcome text,
  callback_scheduled_at timestamptz,
  appointment_at timestamptz,
  is_hot_lead boolean default false,
  followup_urgency text,
  motivation_level int,
  price_floor bigint,
  timeline_urgency text,
  objections text[],
  call_summary text,
  next_best_action text,
  operator_notes text,
  escalated boolean default false,
  priority_callback boolean default false,
  call_brief jsonb,
  call_brief_generated_at timestamptz,
  initial_trust_score numeric default 5.0,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

create index idx_leads_property_id on leads(property_id);
create index idx_leads_stage on leads(stage);
create index idx_leads_owner_phone on leads(owner_phone);
create index idx_leads_callable on leads(callable) where callable = true;
create index idx_leads_call_brief_null on leads(id) where call_brief is null;

alter table leads enable row level security;
create policy leads_service_role on leads for all using (auth.role() = 'service_role');
create policy leads_authenticated_all on leads for all using (auth.role() = 'authenticated');

create table calls (
  id uuid primary key default gen_random_uuid(),
  lead_id uuid references leads(id) on delete cascade,
  signalwire_call_id text,
  direction text default 'inbound',
  call_disposition text,
  duration_seconds int,
  transcript text,
  recording_url text,
  seller_name text,
  property_address_mentioned text,
  asking_price bigint,
  occupancy text,
  property_condition text,
  objections text,
  next_step text,
  call_summary text,
  score_qualification int,
  score_offer_quality int,
  score_objection_handling int,
  score_appointment_booking int,
  score_tone int,
  score_goal_completion int,
  created_at timestamptz default now()
);

create index idx_calls_lead_id on calls(lead_id);
create index idx_calls_signalwire_call_id on calls(signalwire_call_id);
create index idx_calls_disposition on calls(call_disposition);
create index idx_calls_created_at on calls(created_at desc);

alter table calls enable row level security;
create policy calls_service_role on calls for all using (auth.role() = 'service_role');
create policy calls_authenticated_read on calls for select using (auth.role() = 'authenticated');

create table transcript_chunks (
  id uuid primary key default gen_random_uuid(),
  call_id uuid references calls(id) on delete cascade,
  lead_id uuid references leads(id) on delete set null,
  speaker text not null,
  text text not null,
  chunk_type text default 'final',
  sequence_order int not null,
  confidence numeric,
  created_at timestamptz default now()
);

create index idx_transcript_chunks_call_id on transcript_chunks(call_id, sequence_order);

alter table transcript_chunks enable row level security;
create policy transcript_chunks_service_role on transcript_chunks for all using (auth.role() = 'service_role');
create policy transcript_chunks_authenticated_read on transcript_chunks for select using (auth.role() = 'authenticated');

create table call_events (
  id uuid primary key default gen_random_uuid(),
  call_id uuid references calls(id) on delete cascade,
  lead_id uuid references leads(id) on delete set null,
  event_type text not null,
  payload jsonb default '{}',
  created_at timestamptz default now()
);

create index idx_call_events_call_id on call_events(call_id);
create index idx_call_events_created_at on call_events(created_at desc);

alter table call_events enable row level security;
create policy call_events_service_role on call_events for all using (auth.role() = 'service_role');
create policy call_events_authenticated_read on call_events for select using (auth.role() = 'authenticated');

create table comps (
  id uuid primary key default gen_random_uuid(),
  subject_property_id uuid references properties(id) on delete cascade,
  address text,
  sold_price bigint,
  sqft int,
  sold_date date,
  distance_miles numeric,
  source text default 'manual',
  created_at timestamptz default now()
);

create index idx_comps_subject_property_id on comps(subject_property_id);

alter table comps enable row level security;
create policy comps_service_role on comps for all using (auth.role() = 'service_role');
create policy comps_authenticated_all on comps for all using (auth.role() = 'authenticated');

create table offers (
  id uuid primary key default gen_random_uuid(),
  lead_id uuid references leads(id) on delete cascade,
  property_id uuid references properties(id) on delete set null,
  arv_used bigint,
  repair_estimate bigint default 2500000,
  mao_calculated bigint,
  amount bigint,
  status text default 'draft',
  notes text,
  created_by text default 'operator',
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

create index idx_offers_lead_id on offers(lead_id);
create index idx_offers_status on offers(status);

alter table offers enable row level security;
create policy offers_service_role on offers for all using (auth.role() = 'service_role');
create policy offers_authenticated_all on offers for all using (auth.role() = 'authenticated');

create table dnc_list (
  id uuid primary key default gen_random_uuid(),
  phone text unique not null,
  reason text default 'opt_out',
  created_at timestamptz default now()
);

alter table dnc_list enable row level security;
create policy dnc_list_service_role on dnc_list for all using (auth.role() = 'service_role');
create policy dnc_list_authenticated_read on dnc_list for select using (auth.role() = 'authenticated');

create table lead_intel_packets (
  id uuid primary key default gen_random_uuid(),
  lead_id uuid unique references leads(id) on delete cascade,
  packet_state text default 'system_assembled',
  conflict_flags jsonb default '[]',
  compliance_context jsonb default '{}',
  data jsonb default '{}',
  packet_version int default 1,
  updated_at timestamptz default now()
);

alter table lead_intel_packets enable row level security;
create policy lead_intel_packets_service_role on lead_intel_packets for all using (auth.role() = 'service_role');
create policy lead_intel_packets_authenticated_read on lead_intel_packets for select using (auth.role() = 'authenticated');

create table decision_records (
  id uuid primary key default gen_random_uuid(),
  lead_id uuid references leads(id) on delete cascade,
  decision_type text not null,
  inputs_used jsonb,
  output jsonb,
  reason_codes text[],
  confidence numeric,
  version text default '1.0',
  created_at timestamptz default now()
);

create index idx_decision_records_lead_id on decision_records(lead_id);

alter table decision_records enable row level security;
create policy decision_records_service_role on decision_records for all using (auth.role() = 'service_role');
create policy decision_records_authenticated_read on decision_records for select using (auth.role() = 'authenticated');

create table seller_memory (
  id uuid primary key default gen_random_uuid(),
  lead_id uuid unique references leads(id) on delete cascade,
  call_summaries jsonb default '[]',
  motivation_level int,
  timeline_mentioned boolean default false,
  hot_topics jsonb default '[]',
  objections_raised jsonb default '[]',
  competitor_mentions jsonb default '[]',
  price_floor bigint,
  updated_at timestamptz default now()
);

alter table seller_memory enable row level security;
create policy seller_memory_service_role on seller_memory for all using (auth.role() = 'service_role');
create policy seller_memory_authenticated_read on seller_memory for select using (auth.role() = 'authenticated');
