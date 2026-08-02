-- Bob's checkbox ladder asks whether occupancy and condition are known, but
-- nothing extracted them, so those rungs could never be satisfied and every
-- brief after the first call stalled on "condition".
alter table leads add column if not exists occupancy text;
alter table leads add column if not exists property_condition text;
