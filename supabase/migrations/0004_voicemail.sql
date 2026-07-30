-- voicemail_left marks a call that reached an answering machine and had a
-- message played into it, so the dialer can cap repeat voicemails per lead
alter table calls add column if not exists voicemail_left boolean default false;

-- answered_by stores SignalWire's machine-detection verdict (human,
-- machine_end_beep, fax, unknown, ...) so call outcomes stay auditable
alter table calls add column if not exists answered_by text;

-- voicemail_count lets the dialer stop leaving messages after N attempts
-- without counting rows in calls on every dial
alter table leads add column if not exists voicemail_count int default 0;

-- followup_sent guards against duplicate texts when SignalWire retries or
-- re-delivers a status callback for the same call
alter table calls add column if not exists followup_sent boolean default false;

create index if not exists idx_calls_voicemail_left on calls (lead_id, voicemail_left);
