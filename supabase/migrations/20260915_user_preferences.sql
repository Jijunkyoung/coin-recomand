create table if not exists public.user_preferences (
  user_id uuid primary key references auth.users(id) on delete cascade,
  holdings_us text not null default '',
  holdings_kr text not null default '',
  sector_ids text[] not null default '{}',
  coin_email text,
  stock_email text,
  updated_at timestamptz not null default now(),
  constraint sector_ids_known check (
    sector_ids <@ array['defense','semiconductor','energy','ai_platform','mobility','bio','finance','consumer','shipbuilding']::text[]
  ),
  constraint coin_email_reasonable check (coin_email is null or length(coin_email) between 3 and 320),
  constraint stock_email_reasonable check (stock_email is null or length(stock_email) between 3 and 320)
);

alter table public.user_preferences enable row level security;

drop policy if exists "members can read own preferences" on public.user_preferences;
create policy "members can read own preferences"
on public.user_preferences for select to authenticated
using ((select auth.uid()) = user_id);

drop policy if exists "members can create own preferences" on public.user_preferences;
create policy "members can create own preferences"
on public.user_preferences for insert to authenticated
with check ((select auth.uid()) = user_id);

drop policy if exists "members can update own preferences" on public.user_preferences;
create policy "members can update own preferences"
on public.user_preferences for update to authenticated
using ((select auth.uid()) = user_id)
with check ((select auth.uid()) = user_id);

revoke all on table public.user_preferences from anon;
grant select, insert, update on table public.user_preferences to authenticated;
