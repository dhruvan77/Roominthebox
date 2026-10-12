-- Run once: Supabase dashboard -> SQL Editor -> New query -> paste -> Run.
create table if not exists public.sessions (
  id           text primary key,
  task         text not null,
  roles        jsonb not null,
  status       text not null default 'running',   -- running | completed | error | cancelled | interrupted
  final        text,
  conversation text,                               -- the shared conversation (was conversation.txt)
  created_at   timestamptz not null default now()
);

create table if not exists public.events (
  session_id text not null references public.sessions(id) on delete cascade,
  seq        int  not null,
  type       text not null,
  ts         double precision,
  data       jsonb not null default '{}'::jsonb,
  primary key (session_id, seq)
);

-- Lock the tables: only the backend's service_role key can read/write them.
alter table public.sessions enable row level security;
alter table public.events   enable row level security;
