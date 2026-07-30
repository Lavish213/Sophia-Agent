-- Batch outreach: SMS, email, and call-attempt tracking for the outbound dialer.

alter table calls add column if not exists ended_at timestamptz;
create index if not exists idx_calls_active on calls(created_at) where ended_at is null;
create unique index if not exists idx_calls_signalwire_call_id_unique on calls(signalwire_call_id) where signalwire_call_id is not null;

alter table leads add column if not exists email_opted_out boolean default false;

create table sms_messages (
  id uuid primary key default gen_random_uuid(),
  lead_id uuid references leads(id) on delete cascade,
  direction text not null,
  body text not null,
  signalwire_message_sid text,
  status text default 'queued',
  created_at timestamptz default now()
);

create index idx_sms_messages_lead_id on sms_messages(lead_id);

alter table sms_messages enable row level security;
create policy sms_messages_service_role on sms_messages for all using (auth.role() = 'service_role');
create policy sms_messages_authenticated_read on sms_messages for select using (auth.role() = 'authenticated');

create table email_messages (
  id uuid primary key default gen_random_uuid(),
  lead_id uuid references leads(id) on delete cascade,
  direction text not null,
  subject text,
  body text not null,
  provider_message_id text,
  status text default 'queued',
  created_at timestamptz default now()
);

create index idx_email_messages_lead_id on email_messages(lead_id);

alter table email_messages enable row level security;
create policy email_messages_service_role on email_messages for all using (auth.role() = 'service_role');
create policy email_messages_authenticated_read on email_messages for select using (auth.role() = 'authenticated');
