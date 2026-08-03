-- Bob knows more about a lead than its distress score: motivation learned on
-- calls, whether a callback was asked for, how many attempts have already
-- failed. Storing his ranking lets the dialer work the queue in that order
-- instead of a flat sort that ignores everything learned since import.
alter table leads add column if not exists call_priority numeric default 0;
alter table leads add column if not exists priority_reasons text[] default '{}';

create index if not exists idx_leads_call_priority on leads (call_priority desc);

-- waiting_on_human is a tier, not a score: someone who asked for a callback
-- outranks any cold lead no matter how distressed the property is.
alter table leads add column if not exists waiting_on_human boolean default false;

create index if not exists idx_leads_waiting on leads (waiting_on_human, call_priority desc);
