-- Crisis & Connectivity Monitor -- Supabase schema + RLS policies.
--
-- Run this whole file in Supabase Studio -> SQL Editor -> New query -> Run.
-- Safe to re-run: every statement below is idempotent (guards against
-- "already exists" errors), so re-running after a partial/failed attempt
-- is fine and will converge to the correct end state.
--
-- Contains structure only -- no application data -- so it is safe to
-- commit to a public repo.

-- 1. Allowlist of pre-approved e-mail addresses.
-- RLS is enabled with NO policies: this is intentional deny-by-default.
-- Nobody can read or write this table via the API (anon or authenticated
-- key) -- only via the SQL Editor (your own logged-in dashboard session)
-- or the Table Editor UI.
create table if not exists public.allowed_users (
  email text primary key,
  note text,
  created_at timestamptz not null default now()
);

alter table public.allowed_users enable row level security;

-- 2. The gated dataset snapshot (replaces the public App/data/dataset.json).
create table if not exists public.dataset_snapshot (
  id int primary key default 1,
  generated_at timestamptz not null default now(),
  payload jsonb not null,
  constraint dataset_snapshot_singleton check (id = 1)
);

alter table public.dataset_snapshot enable row level security;

-- 3. Allowlist check as a SECURITY DEFINER function, NOT a plain subquery
-- in the policy below.
--
-- Why: allowed_users has its own RLS (deny-by-default, zero policies --
-- see step 1). A plain `exists (select 1 from allowed_users ...)` inside
-- another table's policy is STILL subject to allowed_users' own RLS,
-- evaluated as the CALLING role. For a real `authenticated` session
-- (not a superuser/bypassrls role, which is what a SQL-editor or MCP
-- connection uses), that subquery always saw zero rows -- so the
-- dataset_snapshot policy below denied every allowlisted user, not just
-- non-allowlisted ones. Confirmed by simulating the real role before
-- shipping this fix:
--   set role authenticated;
--   select set_config('request.jwt.claims', '{"email":"<an allowlisted email>"}', true);
--   select count(*) from dataset_snapshot;  -- returned 0, should be 1
-- A SECURITY DEFINER function runs with its owner's privileges (the
-- table owner, which bypasses RLS) regardless of the calling role, so
-- the allowlist check itself works correctly while allowed_users stays
-- fully locked down for direct access (still zero read/write policies).
create or replace function public.is_allowed_user()
returns boolean
language sql
security definer
set search_path = public
stable
as $$
  select exists (
    select 1
    from public.allowed_users au
    where lower(au.email) = lower(auth.jwt() ->> 'email')
  );
$$;

revoke all on function public.is_allowed_user() from public;
grant execute on function public.is_allowed_user() to authenticated;

-- 4. Explicit read policy: only logged-in users whose e-mail is on the
-- allowed_users allowlist (via the function above). No insert/update/
-- delete policies exist on either table, so writes via the API are
-- blocked for everyone (anon and authenticated) -- only the SQL Editor
-- (you, as project owner) can write.
drop policy if exists "allowed users can read dataset snapshot" on public.dataset_snapshot;

create policy "allowed users can read dataset snapshot"
on public.dataset_snapshot
for select
to authenticated
using (public.is_allowed_user());
