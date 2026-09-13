-- Cash snapshots are separate from the synthetic persona and onboarding state.
-- Apply with Supabase migrations, first to the isolated local/staging database.
-- Money is exact integer USD cents; as_of means opening of that calendar day.
-- All writes pass through one owner-scoped, compare-and-swap transaction.
-- https://supabase.com/docs/guides/database/functions#security-definer-vs-invoker

create table public.cash_workspaces (
    user_id uuid primary key references auth.users(id) on delete cascade,
    revision bigint not null check (revision between 1 and 9007199254740991),
    as_of date not null check (as_of between date '1900-01-01' and date '2100-12-31'),
    updated_at timestamptz not null default now()
);

create table public.cash_accounts (
    user_id uuid not null references public.cash_workspaces(user_id) on delete cascade,
    id uuid not null,
    name text not null check (name = btrim(name) and char_length(name) between 1 and 100),
    kind text not null check (kind in ('checking', 'savings')),
    balance_cents bigint not null check (balance_cents between -100000000000 and 100000000000),
    primary key (user_id, id)
);

create table public.cash_bills (
    user_id uuid not null references public.cash_workspaces(user_id) on delete cascade,
    id uuid not null,
    label text not null check (label = btrim(label) and char_length(label) between 1 and 100),
    amount_cents bigint not null check (amount_cents between 1 and 100000000000),
    due_date date not null check (due_date between date '1900-01-01' and date '2100-12-31'),
    primary key (user_id, id)
);

alter table public.cash_workspaces enable row level security;
alter table public.cash_accounts enable row level security;
alter table public.cash_bills enable row level security;

revoke all on public.cash_workspaces, public.cash_accounts, public.cash_bills from anon, authenticated;
grant select on public.cash_workspaces, public.cash_accounts, public.cash_bills to authenticated;

create policy cash_workspaces_read_own on public.cash_workspaces
    for select to authenticated using ((select auth.uid()) = user_id);
create policy cash_accounts_read_own on public.cash_accounts
    for select to authenticated using ((select auth.uid()) = user_id);
create policy cash_bills_read_own on public.cash_bills
    for select to authenticated using ((select auth.uid()) = user_id);

-- One SQL statement sees one consistent snapshot across the three tables.
create function public.get_cash_workspace()
returns jsonb
language sql stable security invoker set search_path = ''
as $$
    select jsonb_build_object(
        'revision', coalesce(w.revision, 0),
        'as_of', w.as_of,
        'currency', 'USD',
        'accounts', coalesce((
            select jsonb_agg(jsonb_build_object(
                'id', a.id, 'name', a.name, 'kind', a.kind, 'balance_cents', a.balance_cents
            ) order by a.id)
            from public.cash_accounts a where a.user_id = auth.uid()
        ), '[]'::jsonb),
        'bills', coalesce((
            select jsonb_agg(jsonb_build_object(
                'id', b.id, 'label', b.label, 'amount_cents', b.amount_cents, 'due_date', b.due_date
            ) order by b.due_date, b.id)
            from public.cash_bills b where b.user_id = auth.uid()
        ), '[]'::jsonb)
    )
    from (select 1) anchor
    left join public.cash_workspaces w on w.user_id = auth.uid();
$$;

create function public.save_cash_workspace(
    p_expected_revision bigint,
    p_as_of date,
    p_accounts jsonb,
    p_bills jsonb
)
returns jsonb
language plpgsql security definer set search_path = ''
as $$
declare
    owner_id uuid := auth.uid();
    current_revision bigint;
begin
    if owner_id is null then
        raise exception using errcode = '42501', message = 'Authentication required.';
    end if;
    if p_expected_revision is null or p_expected_revision < 0 or p_expected_revision >= 9007199254740991 then
        raise exception using errcode = '22023', message = 'Invalid workspace revision.';
    end if;
    if p_as_of is null or p_as_of not between date '1900-01-01' and date '2100-12-31' then
        raise exception using errcode = '22023', message = 'Invalid balance date.';
    end if;
    if p_accounts is null or jsonb_typeof(p_accounts) <> 'array'
        or p_bills is null or jsonb_typeof(p_bills) <> 'array' then
        raise exception using errcode = '22023', message = 'Accounts and bills must be arrays.';
    end if;
    if jsonb_array_length(p_accounts) > 50 or jsonb_array_length(p_bills) > 200 then
        raise exception using errcode = '22023', message = 'At most 50 accounts and 200 bills can be saved.';
    end if;
    if exists (
        select 1 from jsonb_array_elements(p_accounts) a
        where jsonb_typeof(a) <> 'object'
            or jsonb_typeof(a->'balance_cents') is distinct from 'number'
            or (a->>'balance_cents') !~ '^-?[0-9]+$'
            or jsonb_typeof(a->'name') is distinct from 'string'
            or jsonb_typeof(a->'kind') is distinct from 'string'
            or jsonb_typeof(a->'id') is distinct from 'string'
    ) or exists (
        select 1 from jsonb_array_elements(p_bills) b
        where jsonb_typeof(b) <> 'object'
            or jsonb_typeof(b->'amount_cents') is distinct from 'number'
            or (b->>'amount_cents') !~ '^[0-9]+$'
            or jsonb_typeof(b->'label') is distinct from 'string'
            or jsonb_typeof(b->'id') is distinct from 'string'
            or jsonb_typeof(b->'due_date') is distinct from 'string'
            or (b->>'due_date') !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
    ) then
        raise exception using errcode = '22023', message = 'Invalid account or bill fields; amounts must be integer cents.';
    end if;

    -- The first writer creates revision 1. Concurrent creation waits here;
    -- subsequent writers lock the same owner row before checking the revision.
    if p_expected_revision = 0 then
        insert into public.cash_workspaces (user_id, revision, as_of)
            values (owner_id, 1, p_as_of)
            on conflict (user_id) do nothing;
        if not found then
            raise exception using errcode = '40001', message = 'Workspace changed. Reload before saving.';
        end if;
    else
        select revision into current_revision from public.cash_workspaces
            where user_id = owner_id for update;
        if current_revision is distinct from p_expected_revision then
            raise exception using errcode = '40001', message = 'Workspace changed. Reload before saving.';
        end if;
        update public.cash_workspaces set revision = revision + 1, as_of = p_as_of, updated_at = now()
            where user_id = owner_id;
    end if;

    delete from public.cash_accounts where user_id = owner_id;
    insert into public.cash_accounts (user_id, id, name, kind, balance_cents)
        select owner_id, a.id, a.name, a.kind, a.balance_cents
        from jsonb_to_recordset(p_accounts) as a(id uuid, name text, kind text, balance_cents bigint);
    delete from public.cash_bills where user_id = owner_id;
    insert into public.cash_bills (user_id, id, label, amount_cents, due_date)
        select owner_id, b.id, b.label, b.amount_cents, b.due_date
        from jsonb_to_recordset(p_bills) as b(id uuid, label text, amount_cents bigint, due_date date);

    return public.get_cash_workspace();
end;
$$;

revoke all on function public.get_cash_workspace() from public, anon;
revoke all on function public.save_cash_workspace(bigint, date, jsonb, jsonb) from public, anon;
grant execute on function public.get_cash_workspace() to authenticated;
grant execute on function public.save_cash_workspace(bigint, date, jsonb, jsonb) to authenticated;
