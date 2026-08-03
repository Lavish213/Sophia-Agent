-- Imported list data is frequently wrong: disconnected numbers, LLCs where a
-- person should be, PO boxes, duplicate rows. Recording what looked wrong at
-- import means a bad row can be reviewed instead of silently dialed.
alter table properties add column if not exists data_issues text[] default '{}';
alter table properties add column if not exists data_confidence numeric default 1.0;

create index if not exists idx_properties_data_confidence
  on properties (data_confidence);
