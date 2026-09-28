create table if not exists public.stock_broker_sync_state (
  user_id uuid not null references auth.users(id) on delete cascade,
  broker text not null check (broker in ('toss')),
  positions jsonb not null default '[]'::jsonb,
  source text not null default 'local_pc' check (source in ('local_pc')),
  synced_at timestamptz not null default now(),
  primary key (user_id, broker)
);

alter table public.stock_broker_sync_state enable row level security;

drop policy if exists "members can read own broker sync state" on public.stock_broker_sync_state;
create policy "members can read own broker sync state"
on public.stock_broker_sync_state for select to authenticated
using ((select auth.uid()) = user_id);

revoke all on table public.stock_broker_sync_state from anon;
grant select on table public.stock_broker_sync_state to authenticated;
