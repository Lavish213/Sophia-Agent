-- One row per worker cycle. Without this the only evidence a worker ran is
-- stdout on Railway, which means a process that dies quietly costs a day of
-- calls before anyone notices.
create table if not exists worker_runs (
  id uuid primary key default gen_random_uuid(),
  worker text not null,
  started_at timestamptz not null default now(),
  finished_at timestamptz,
  status text not null default 'running',
  results jsonb default '{}',
  error text,
  duration_ms int
);

create index if not exists idx_worker_runs_recent on worker_runs (worker, started_at desc);

alter table worker_runs enable row level security;

create policy "service_role_all_worker_runs" on worker_runs
  for all to service_role using (true) with check (true);
create policy "authenticated_read_worker_runs" on worker_runs
  for select to authenticated using (true);
