-- 0001_onboarding.sql — Phase 1 onboarding schema.
--
-- Originally applied through the hosted Dashboard SQL Editor. New local
-- stacks apply this through the CLI. Reconcile the hosted migration history
-- before promotion; do not reset hosted accounts to replay migrations.
--
-- Patterns per Supabase docs:
--   https://supabase.com/docs/guides/auth/managing-user-data
--   https://supabase.com/docs/guides/database/postgres/row-level-security

create table if not exists public.profiles (
	id uuid primary key references auth.users (id) on delete cascade,
	first_name text,
	last_name text,
	-- 1 = welcome, 2 = setup path, 3 = review/finish.
	onboarding_step integer not null default 1 check (onboarding_step between 1 and 3),
	onboarding_completed boolean not null default false,
	setup_path text check (setup_path in ('manual', 'sample', 'import')),
	created_at timestamptz not null default now(),
	updated_at timestamptz not null default now()
);

alter table public.profiles enable row level security;

-- anon never touches profiles; authenticated may read and maintain only
-- the row whose id equals the caller's auth uid.
revoke all on public.profiles from anon;
grant select, insert, update on public.profiles to authenticated;

drop policy if exists "profiles_select_own" on public.profiles;
create policy "profiles_select_own" on public.profiles
	for select to authenticated
	using ((select auth.uid()) = id);

drop policy if exists "profiles_insert_own" on public.profiles;
create policy "profiles_insert_own" on public.profiles
	for insert to authenticated
	with check ((select auth.uid()) = id);

drop policy if exists "profiles_update_own" on public.profiles;
create policy "profiles_update_own" on public.profiles
	for update to authenticated
	using ((select auth.uid()) = id)
	with check ((select auth.uid()) = id);

-- updated_at maintenance.
create or replace function public.touch_updated_at()
returns trigger
language plpgsql
as $$
begin
	new.updated_at = now();
	return new;
end;
$$;

drop trigger if exists profiles_touch_updated_at on public.profiles;
create trigger profiles_touch_updated_at
	before update on public.profiles
	for each row execute function public.touch_updated_at();

-- Auto-create a profile on signup, seeding names from user_metadata.
-- security definer so the trigger can insert into public.profiles
-- regardless of the caller's role; search_path pinned per Supabase docs.
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer set search_path = public
as $$
begin
	insert into public.profiles (id, first_name, last_name)
	values (
		new.id,
		nullif(new.raw_user_meta_data ->> 'first_name', ''),
		nullif(new.raw_user_meta_data ->> 'last_name', '')
	)
	on conflict (id) do nothing;
	return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
	after insert on auth.users
	for each row execute function public.handle_new_user();

-- Backfill for users created before this migration ran.
insert into public.profiles (id, first_name, last_name)
select
	u.id,
	nullif(u.raw_user_meta_data ->> 'first_name', ''),
	nullif(u.raw_user_meta_data ->> 'last_name', '')
from auth.users u
on conflict (id) do nothing;
