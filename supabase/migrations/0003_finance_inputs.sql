-- 0003_finance_inputs.sql — canonical supplemental personal-finance snapshots.
--
-- Cash and supplemental inputs share one owner-scoped revision. Both public
-- writers validate the complete resulting workspace before the private cash
-- persistence primitive performs the compare-and-swap transaction.
--
-- Security patterns:
-- https://supabase.com/docs/guides/database/functions
-- https://supabase.com/docs/guides/database/postgres/row-level-security

create table if not exists public.financial_inputs (
    user_id uuid primary key references public.cash_workspaces(user_id) on delete cascade,
    inputs jsonb not null check (
        jsonb_typeof(inputs) = 'object'
        and octet_length(inputs::text) <= 4000000
    ),
    updated_at timestamptz not null default now()
);

alter table public.financial_inputs enable row level security;

-- The browser may read only its own canonical record. All writes are confined
-- to the security-definer CAS RPC below so no direct write can bypass revision
-- control or validation.
revoke all on table public.financial_inputs from public, anon, authenticated;
grant select on table public.financial_inputs to authenticated;

drop policy if exists financial_inputs_read_own on public.financial_inputs;
create policy financial_inputs_read_own on public.financial_inputs
    for select to authenticated using ((select auth.uid()) = user_id);

-- Small, non-public validation primitives.  They never cast untrusted date or
-- numeric JSON before proving its shape, so malformed RPC payloads consistently
-- become the public 22023 validation error instead of a database implementation
-- error.
create or replace function public.finance_is_valid_date(p_value text)
returns boolean
language plpgsql immutable set search_path = ''
as $$
declare
    parsed_date date;
begin
    if p_value is null or p_value !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' then
        return false;
    end if;
    begin
        parsed_date := p_value::date;
    exception when others then
        return false;
    end;
    return parsed_date between date '1900-01-01' and date '2100-12-31'
        and to_char(parsed_date, 'YYYY-MM-DD') = p_value;
end;
$$;

create or replace function public.finance_object_has_only_keys(p_value jsonb, p_allowed text[])
returns boolean
language plpgsql immutable set search_path = ''
as $$
begin
    if jsonb_typeof(p_value) is distinct from 'object' then
        return false;
    end if;
    return not exists (
        select 1
        from jsonb_object_keys(p_value) as fields(key)
        where fields.key <> all(p_allowed)
    );
end;
$$;

create or replace function public.finance_is_json_string(p_value jsonb, p_min_length integer, p_max_length integer)
returns boolean
language plpgsql immutable set search_path = ''
as $$
declare
    text_value text;
begin
    if jsonb_typeof(p_value) is distinct from 'string' then
        return false;
    end if;
    text_value := p_value #>> '{}';
    -- Match Python str.strip(), independent of the database locale.
    return char_length(text_value) between p_min_length and p_max_length
        and text_value = btrim(text_value, U&'\0009\000A\000B\000C\000D\001C\001D\001E\001F\0020\0085\00A0\1680\2000\2001\2002\2003\2004\2005\2006\2007\2008\2009\200A\2028\2029\202F\205F\3000');
end;
$$;

create or replace function public.finance_is_json_uuid(p_value jsonb)
returns boolean
language sql immutable set search_path = ''
as $$
    select coalesce(
        jsonb_typeof(p_value) = 'string'
        and (p_value #>> '{}') ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
        false
    );
$$;

create or replace function public.finance_is_json_integer(p_value jsonb, p_min numeric, p_max numeric)
returns boolean
language plpgsql immutable set search_path = ''
as $$
declare
    text_value text;
    parsed_number numeric;
begin
    if jsonb_typeof(p_value) is distinct from 'number' then
        return false;
    end if;
    text_value := p_value #>> '{}';
    if text_value !~ '^-?[0-9]+$' or char_length(text_value) > 20 then
        return false;
    end if;
    begin
        parsed_number := text_value::numeric;
    exception when others then
        return false;
    end;
    return parsed_number between p_min and p_max;
end;
$$;

create or replace function public.finance_is_json_number(p_value jsonb, p_min numeric, p_max numeric)
returns boolean
language plpgsql immutable set search_path = ''
as $$
declare
    text_value text;
    parsed_number numeric;
begin
    if jsonb_typeof(p_value) is distinct from 'number' then
        return false;
    end if;
    text_value := p_value #>> '{}';
    if char_length(text_value) > 100 then
        return false;
    end if;
    begin
        parsed_number := text_value::numeric;
    exception when others then
        return false;
    end;
    return parsed_number between p_min and p_max;
end;
$$;

create or replace function public.finance_is_json_number_above(
    p_value jsonb,
    p_lower numeric,
    p_max numeric
)
returns boolean
language plpgsql immutable set search_path = ''
as $$
declare
    text_value text;
    parsed_number numeric;
begin
    if jsonb_typeof(p_value) is distinct from 'number' then
        return false;
    end if;
    text_value := p_value #>> '{}';
    if char_length(text_value) > 100 then
        return false;
    end if;
    begin
        parsed_number := text_value::numeric;
    exception when others then
        return false;
    end;
    return parsed_number > p_lower and parsed_number <= p_max;
end;
$$;

create or replace function public.finance_is_json_boolean(p_value jsonb)
returns boolean
language sql immutable set search_path = ''
as $$
    select coalesce(jsonb_typeof(p_value) = 'boolean', false);
$$;
create or replace function public.finance_is_json_array(p_value jsonb, p_min_length integer, p_max_length integer)
returns boolean
language plpgsql immutable set search_path = ''
as $$
begin
    if p_min_length < 0 or p_max_length < p_min_length
        or jsonb_typeof(p_value) is distinct from 'array' then
        return false;
    end if;
    return jsonb_array_length(p_value) between p_min_length and p_max_length;
end;
$$;


create or replace function public.finance_is_rule_occurrence(
    p_anchor date,
    p_recurrence text,
    p_due_date date
)
returns boolean
language plpgsql immutable set search_path = ''
as $$
declare
    month_offset integer;
    expected_date date;
begin
    if p_due_date < p_anchor then
        return false;
    end if;
    if p_recurrence = 'none' then
        return p_due_date = p_anchor;
    end if;
    if p_recurrence = 'weekly' then
        return mod(p_due_date - p_anchor, 7) = 0;
    end if;
    if p_recurrence = 'biweekly' then
        return mod(p_due_date - p_anchor, 14) = 0;
    end if;
    if p_recurrence = 'monthly' then
        month_offset := (extract(year from p_due_date)::integer - extract(year from p_anchor)::integer) * 12
            + extract(month from p_due_date)::integer - extract(month from p_anchor)::integer;
        expected_date := make_date(
            extract(year from p_due_date)::integer,
            extract(month from p_due_date)::integer,
            least(
                extract(day from p_anchor)::integer,
                extract(day from (date_trunc('month', p_due_date) + interval '1 month - 1 day'))::integer
            )
        );
        return month_offset >= 0 and p_due_date = expected_date;
    end if;
    if p_recurrence = 'yearly' then
        expected_date := make_date(
            extract(year from p_due_date)::integer,
            extract(month from p_anchor)::integer,
            least(
                extract(day from p_anchor)::integer,
                extract(day from (
                    date_trunc('month', make_date(extract(year from p_due_date)::integer, extract(month from p_anchor)::integer, 1))
                    + interval '1 month - 1 day'
                ))::integer
            )
        );
        return extract(year from p_due_date)::integer >= extract(year from p_anchor)::integer
            and extract(month from p_due_date)::integer = extract(month from p_anchor)::integer
            and p_due_date = expected_date;
    end if;
    return false;
end;
$$;

create or replace function public.finance_validate_cash_account(p_account jsonb)
returns void
language plpgsql set search_path = ''
as $$
begin
    if not public.finance_object_has_only_keys(p_account, array['id', 'name', 'kind', 'balance_cents'])
        or not public.finance_is_json_uuid(p_account->'id')
        or not public.finance_is_json_string(p_account->'name', 1, 100)
        or jsonb_typeof(p_account->'kind') is distinct from 'string'
        or p_account->>'kind' not in ('checking', 'savings')
        or not public.finance_is_json_integer(p_account->'balance_cents', -100000000000, 100000000000) then
        raise exception using errcode = '22023', message = 'Invalid cash account fields.';
    end if;
end;
$$;

create or replace function public.finance_validate_cash_bill(p_bill jsonb)
returns void
language plpgsql set search_path = ''
as $$
begin
    if not public.finance_object_has_only_keys(p_bill, array['id', 'label', 'amount_cents', 'due_date'])
        or not public.finance_is_json_uuid(p_bill->'id')
        or not public.finance_is_json_string(p_bill->'label', 1, 100)
        or not public.finance_is_json_integer(p_bill->'amount_cents', 1, 100000000000)
        or jsonb_typeof(p_bill->'due_date') is distinct from 'string'
        or not public.finance_is_valid_date(p_bill->>'due_date') then
        raise exception using errcode = '22023', message = 'Invalid cash-flow event fields.';
    end if;
end;
$$;

create or replace function public.finance_validate_cash_snapshot(p_accounts jsonb, p_bills jsonb)
returns void
language plpgsql set search_path = ''
as $$
declare
    item jsonb;
begin
    if not public.finance_is_json_array(p_accounts, 0, 50)
        or not public.finance_is_json_array(p_bills, 0, 200) then
        raise exception using errcode = '22023', message = 'Invalid cash workspace collections.';
    end if;

    for item in select value from jsonb_array_elements(p_accounts) loop
        perform public.finance_validate_cash_account(item);
    end loop;
    for item in select value from jsonb_array_elements(p_bills) loop
        perform public.finance_validate_cash_bill(item);
    end loop;

    if exists (
        select lower(entries.item->>'id')
        from jsonb_array_elements(p_accounts) as entries(item)
        group by lower(entries.item->>'id')
        having count(*) > 1
    ) then
        raise exception using errcode = '22023', message = 'Cash account IDs must be unique.';
    end if;
    if exists (
        select lower(entries.item->>'id')
        from jsonb_array_elements(p_bills) as entries(item)
        group by lower(entries.item->>'id')
        having count(*) > 1
    ) then
        raise exception using errcode = '22023', message = 'Cash bill IDs must be unique.';
    end if;
end;
$$;

create or replace function public.finance_validate_cash_bill_array(p_bills jsonb, p_label text)
returns void
language plpgsql set search_path = ''
as $$
declare
    item jsonb;
begin
    if not public.finance_is_json_array(p_bills, 0, 200) then
        raise exception using errcode = '22023', message = 'Invalid scenario cash-flow collection.';
    end if;
    for item in select value from jsonb_array_elements(p_bills) loop
        perform public.finance_validate_cash_bill(item);
    end loop;
    if exists (
        select lower(entries.item->>'id')
        from jsonb_array_elements(p_bills) as entries(item)
        group by lower(entries.item->>'id')
        having count(*) > 1
    ) then
        raise exception using errcode = '22023', message = p_label || ' IDs must be unique.';
    end if;
end;
$$;

create or replace function public.finance_validate_assumptions(p_assumptions jsonb)
returns void
language plpgsql set search_path = ''
as $$
begin
    if not public.finance_object_has_only_keys(
        p_assumptions,
        array[
            'monthly_variable_income_cents', 'monthly_essential_spending_cents',
            'monthly_discretionary_spending_cents', 'income_variability_pct',
            'spending_variability_pct', 'persistence_days', 'income_spending_correlation',
            'market_assumptions_enabled', 'expected_annual_return_pct',
            'annual_return_volatility_pct', 'income_market_correlation'
        ]
    )
        or not public.finance_is_json_integer(p_assumptions->'monthly_variable_income_cents', 0, 100000000000)
        or not public.finance_is_json_integer(p_assumptions->'monthly_essential_spending_cents', 0, 100000000000)
        or not public.finance_is_json_integer(p_assumptions->'monthly_discretionary_spending_cents', 0, 100000000000)
        or not public.finance_is_json_number(p_assumptions->'income_variability_pct', 0, 2)
        or not public.finance_is_json_number(p_assumptions->'spending_variability_pct', 0, 2)
        or not public.finance_is_json_integer(p_assumptions->'persistence_days', 1, 30)
        or not public.finance_is_json_number(p_assumptions->'income_spending_correlation', -0.95, 0.95)
        or not public.finance_is_json_boolean(p_assumptions->'market_assumptions_enabled')
        or not public.finance_is_json_number(p_assumptions->'expected_annual_return_pct', -0.99, 2)
        or not public.finance_is_json_number(p_assumptions->'annual_return_volatility_pct', 0, 2)
        or not public.finance_is_json_number(p_assumptions->'income_market_correlation', -0.95, 0.95) then
        raise exception using errcode = '22023', message = 'Invalid model assumptions.';
    end if;
end;
$$;

create or replace function public.finance_validate_history_transaction(p_transaction jsonb)
returns void
language plpgsql set search_path = ''
as $$
declare
    amount numeric;
    category text;
begin
    if not public.finance_object_has_only_keys(
        p_transaction,
        array['id', 'date', 'description', 'amount_cents', 'category', 'source_key']
    )
        or not public.finance_is_json_uuid(p_transaction->'id')
        or jsonb_typeof(p_transaction->'date') is distinct from 'string'
        or not public.finance_is_valid_date(p_transaction->>'date')
        or not public.finance_is_json_string(p_transaction->'description', 1, 500)
        or not public.finance_is_json_integer(p_transaction->'amount_cents', -100000000000, 100000000000)
        or jsonb_typeof(p_transaction->'category') is distinct from 'string'
        or p_transaction->>'category' not in (
            'income_fixed', 'income_variable', 'expense_fixed',
            'expense_essential_variable', 'expense_discretionary_variable',
            'expense_irregular', 'transfer', 'credit_purchase', 'credit_payment',
            'investment_buy', 'investment_sell'
        )
        or (
            jsonb_typeof(p_transaction->'source_key') is distinct from 'null'
            and not public.finance_is_json_string(p_transaction->'source_key', 1, 200)
        ) then
        raise exception using errcode = '22023', message = 'Invalid historical transaction fields.';
    end if;

    amount := (p_transaction->>'amount_cents')::numeric;
    category := p_transaction->>'category';
    if amount = 0
        or (category in ('income_fixed', 'income_variable', 'investment_sell') and amount <= 0)
        or (category in (
            'expense_fixed', 'expense_essential_variable', 'expense_discretionary_variable',
            'expense_irregular', 'credit_purchase', 'credit_payment', 'investment_buy'
        ) and amount >= 0) then
        raise exception using errcode = '22023', message = 'Historical transaction cents do not match their category.';
    end if;
end;
$$;

create or replace function public.finance_validate_credit_account(p_credit jsonb)
returns void
language plpgsql set search_path = ''
as $$
begin
    if not public.finance_object_has_only_keys(
        p_credit,
        array[
            'id', 'name', 'credit_limit_cents', 'current_balance_cents', 'purchase_apr',
            'statement_close_day', 'payment_due_day', 'grace_period_eligible', 'minimum_payment_cents'
        ]
    )
        or not public.finance_is_json_uuid(p_credit->'id')
        or not public.finance_is_json_string(p_credit->'name', 1, 100)
        or not public.finance_is_json_integer(p_credit->'credit_limit_cents', 0, 100000000000)
        or not public.finance_is_json_integer(p_credit->'current_balance_cents', 0, 100000000000)
        or not public.finance_is_json_number(p_credit->'purchase_apr', 0, 1)
        or not public.finance_is_json_integer(p_credit->'statement_close_day', 1, 28)
        or not public.finance_is_json_integer(p_credit->'payment_due_day', 1, 28)
        or not public.finance_is_json_boolean(p_credit->'grace_period_eligible')
        or not public.finance_is_json_integer(p_credit->'minimum_payment_cents', 0, 100000000000) then
        raise exception using errcode = '22023', message = 'Invalid credit account fields.';
    end if;
end;
$$;

create or replace function public.finance_validate_holding(p_holding jsonb)
returns void
language plpgsql set search_path = ''
as $$
declare
    lot jsonb;
begin
    if not public.finance_object_has_only_keys(
        p_holding,
        array['id', 'symbol', 'account', 'current_price_cents', 'tax_lots']
    )
        or not public.finance_is_json_uuid(p_holding->'id')
        or not public.finance_is_json_string(p_holding->'symbol', 1, 32)
        or jsonb_typeof(p_holding->'account') is distinct from 'string'
        or p_holding->>'account' not in ('taxable', 'retirement')
        or not public.finance_is_json_integer(p_holding->'current_price_cents', 1, 100000000000)
        or not public.finance_is_json_array(p_holding->'tax_lots', 0, 1000) then
        raise exception using errcode = '22023', message = 'Invalid holding fields.';
    end if;
    for lot in select value from jsonb_array_elements(p_holding->'tax_lots') loop
        if not public.finance_object_has_only_keys(
            lot,
            array['id', 'quantity', 'cost_basis_per_share_cents', 'purchase_date']
        )
            or not public.finance_is_json_uuid(lot->'id')
            or not public.finance_is_json_number_above(lot->'quantity', 0, 1000000000000)
            or not public.finance_is_json_integer(lot->'cost_basis_per_share_cents', 0, 100000000000)
            or jsonb_typeof(lot->'purchase_date') is distinct from 'string'
            or not public.finance_is_valid_date(lot->>'purchase_date') then
            raise exception using errcode = '22023', message = 'Invalid tax-lot fields.';
        end if;
    end loop;
    if exists (
        select lower(entries.item->>'id')
        from jsonb_array_elements(p_holding->'tax_lots') as entries(item)
        group by lower(entries.item->>'id')
        having count(*) > 1
    ) then
        raise exception using errcode = '22023', message = 'Tax-lot IDs must be unique.';
    end if;
end;
$$;

create or replace function public.finance_validate_policy(p_policy jsonb)
returns void
language plpgsql set search_path = ''
as $$
declare
    priority jsonb;
begin
    if not public.finance_object_has_only_keys(
        p_policy,
        array[
            'operating_buffer_cents', 'coverage_target', 'max_credit_utilization', 'priorities',
            'settlement_days', 'external_transfer_days', 'capital_gains_rate', 'overdraft_apr',
            'buffer_tolerance_dollar_days', 'lot_selection'
        ]
    )
        or not public.finance_is_json_integer(p_policy->'operating_buffer_cents', 0, 100000000000)
        or not public.finance_is_json_number_above(p_policy->'coverage_target', 0, 1)
        or not public.finance_is_json_number(p_policy->'max_credit_utilization', 0, 1)
        or not public.finance_is_json_array(p_policy->'priorities', 1, 3)
        or not public.finance_is_json_integer(p_policy->'settlement_days', 0, 30)
        or not public.finance_is_json_integer(p_policy->'external_transfer_days', 0, 30)
        or not public.finance_is_json_number(p_policy->'capital_gains_rate', 0, 1)
        or not public.finance_is_json_number(p_policy->'overdraft_apr', 0, 1)
        or (
            jsonb_typeof(p_policy->'buffer_tolerance_dollar_days') is distinct from 'null'
            and not public.finance_is_json_number(p_policy->'buffer_tolerance_dollar_days', 0, 1000000000000000)
        )
        or jsonb_typeof(p_policy->'lot_selection') is distinct from 'string'
        or p_policy->>'lot_selection' not in ('fifo', 'hifo') then
        raise exception using errcode = '22023', message = 'Invalid planning policy.';
    end if;
    for priority in select value from jsonb_array_elements(p_policy->'priorities') loop
        if jsonb_typeof(priority) is distinct from 'string'
            or priority #>> '{}' not in (
                'avoid_interest_bearing_debt', 'minimize_taxable_sales', 'minimize_deferred_spending'
            ) then
            raise exception using errcode = '22023', message = 'Invalid planning priority.';
        end if;
    end loop;
    if exists (
        select entries.item #>> '{}'
        from jsonb_array_elements(p_policy->'priorities') as entries(item)
        group by entries.item #>> '{}'
        having count(*) > 1
    ) then
        raise exception using errcode = '22023', message = 'Planning priorities cannot repeat.';
    end if;
end;
$$;

create or replace function public.finance_validate_event_rules(
    p_rules jsonb,
    p_bills jsonb,
    p_income_events jsonb
)
returns void
language plpgsql set search_path = ''
as $$
declare
    rule jsonb;
    settlement jsonb;
    event jsonb;
    anchor_date date;
    end_date date;
    due_date date;
begin
    if not public.finance_is_json_array(p_rules, 0, 400) then
        raise exception using errcode = '22023', message = 'Invalid event rule collection.';
    end if;

    if exists (
        select lower(events.item->>'id')
        from (
            select item from jsonb_array_elements(p_bills) as bills(item)
            union all
            select item from jsonb_array_elements(p_income_events) as income(item)
        ) as events
        group by lower(events.item->>'id')
        having count(*) > 1
    ) then
        raise exception using errcode = '22023', message = 'Cash-flow event IDs must be unique.';
    end if;

    for rule in select value from jsonb_array_elements(p_rules) loop
        if not public.finance_object_has_only_keys(
            rule,
            array['event_id', 'recurrence', 'end_date', 'settlements']
        )
            or not public.finance_is_json_uuid(rule->'event_id')
            or jsonb_typeof(rule->'recurrence') is distinct from 'string'
            or rule->>'recurrence' not in ('none', 'weekly', 'biweekly', 'monthly', 'yearly')
            or (
                jsonb_typeof(rule->'end_date') is distinct from 'string'
                and jsonb_typeof(rule->'end_date') is distinct from 'null'
            )
            or (
                jsonb_typeof(rule->'end_date') = 'string'
                and not public.finance_is_valid_date(rule->>'end_date')
            )
            or not public.finance_is_json_array(rule->'settlements', 0, 10000) then
            raise exception using errcode = '22023', message = 'Invalid event rule fields.';
        end if;
        if rule->>'recurrence' = 'none' and jsonb_typeof(rule->'end_date') is distinct from 'null' then
            raise exception using errcode = '22023', message = 'One-time events cannot have a recurrence end date.';
        end if;

        select events.item into event
        from (
            select item from jsonb_array_elements(p_bills) as bills(item)
            union all
            select item from jsonb_array_elements(p_income_events) as income(item)
        ) as events
        where lower(events.item->>'id') = lower(rule->>'event_id')
        limit 1;
        if event is null then
            raise exception using errcode = '22023', message = 'Event rules must refer to a saved bill or income event.';
        end if;

        anchor_date := (event->>'due_date')::date;
        if jsonb_typeof(rule->'end_date') = 'string' then
            end_date := (rule->>'end_date')::date;
            if end_date < anchor_date then
                raise exception using errcode = '22023', message = 'Recurrence end dates cannot precede their event date.';
            end if;
        else
            end_date := null;
        end if;

        for settlement in select value from jsonb_array_elements(rule->'settlements') loop
            if not public.finance_object_has_only_keys(
                settlement,
                array['due_date', 'status', 'settled_on']
            )
                or jsonb_typeof(settlement->'due_date') is distinct from 'string'
                or not public.finance_is_valid_date(settlement->>'due_date')
                or jsonb_typeof(settlement->'status') is distinct from 'string'
                or settlement->>'status' not in ('settled', 'skipped')
                or (
                    jsonb_typeof(settlement->'settled_on') is distinct from 'string'
                    and jsonb_typeof(settlement->'settled_on') is distinct from 'null'
                )
                or (
                    jsonb_typeof(settlement->'settled_on') = 'string'
                    and not public.finance_is_valid_date(settlement->>'settled_on')
                )
                or (settlement->>'status' = 'settled' and jsonb_typeof(settlement->'settled_on') is distinct from 'string')
                or (settlement->>'status' = 'skipped' and jsonb_typeof(settlement->'settled_on') is distinct from 'null') then
                raise exception using errcode = '22023', message = 'Invalid event settlement fields.';
            end if;
            due_date := (settlement->>'due_date')::date;
            if end_date is not null and due_date > end_date then
                raise exception using errcode = '22023', message = 'Settlements cannot be after the recurrence end date.';
            end if;
            if not public.finance_is_rule_occurrence(anchor_date, rule->>'recurrence', due_date) then
                raise exception using errcode = '22023', message = 'Settlement dates must match an event occurrence.';
            end if;
        end loop;

        if exists (
            select entries.item->>'due_date'
            from jsonb_array_elements(rule->'settlements') as entries(item)
            group by entries.item->>'due_date'
            having count(*) > 1
        ) then
            raise exception using errcode = '22023', message = 'Each event occurrence can be settled only once.';
        end if;
    end loop;

    if exists (
        select lower(entries.item->>'event_id')
        from jsonb_array_elements(p_rules) as entries(item)
        group by lower(entries.item->>'event_id')
        having count(*) > 1
    ) then
        raise exception using errcode = '22023', message = 'Event rules cannot repeat an event.';
    end if;
end;
$$;

create or replace function public.finance_validate_scenarios(
    p_scenarios jsonb,
    p_base_bills jsonb,
    p_base_income_events jsonb,
    p_base_event_rules jsonb
)
returns void
language plpgsql set search_path = ''
as $$
declare
    scenario jsonb;
    overrides jsonb;
    scenario_bills jsonb;
    scenario_income_events jsonb;
    scenario_event_rules jsonb;
begin
    if not public.finance_is_json_array(p_scenarios, 0, 20) then
        raise exception using errcode = '22023', message = 'Invalid named scenario collection.';
    end if;

    for scenario in select value from jsonb_array_elements(p_scenarios) loop
        if not public.finance_object_has_only_keys(scenario, array['id', 'name', 'base_revision', 'overrides'])
            or not public.finance_is_json_uuid(scenario->'id')
            or not public.finance_is_json_string(scenario->'name', 1, 100)
            or not public.finance_is_json_integer(scenario->'base_revision', 0, 9007199254740991)
            or jsonb_typeof(scenario->'overrides') is distinct from 'object' then
            raise exception using errcode = '22023', message = 'Invalid named scenario fields.';
        end if;
        overrides := scenario->'overrides';
        if not public.finance_object_has_only_keys(
            overrides,
            array['bills', 'income_events', 'event_rules', 'assumptions', 'policy', 'mode']
        ) then
            raise exception using errcode = '22023', message = 'Invalid named scenario overrides.';
        end if;

        if overrides ? 'bills' then
            perform public.finance_validate_cash_bill_array(overrides->'bills', 'Scenario bill');
            scenario_bills := overrides->'bills';
        else
            scenario_bills := p_base_bills;
        end if;
        if overrides ? 'income_events' then
            perform public.finance_validate_cash_bill_array(overrides->'income_events', 'Scenario income event');
            scenario_income_events := overrides->'income_events';
        else
            scenario_income_events := p_base_income_events;
        end if;
        if overrides ? 'assumptions' then
            perform public.finance_validate_assumptions(overrides->'assumptions');
        end if;
        if overrides ? 'policy' then
            perform public.finance_validate_policy(overrides->'policy');
        end if;
        if overrides ? 'mode' and (
            jsonb_typeof(overrides->'mode') is distinct from 'string'
            or overrides->>'mode' not in ('scheduled', 'assumptions', 'history')
        ) then
            raise exception using errcode = '22023', message = 'Invalid named scenario mode.';
        end if;

        if overrides ? 'event_rules' then
            scenario_event_rules := overrides->'event_rules';
        else
            scenario_event_rules := p_base_event_rules;
        end if;
        perform public.finance_validate_event_rules(
            scenario_event_rules,
            scenario_bills,
            scenario_income_events
        );
    end loop;

    if exists (
        select lower(entries.item->>'id')
        from jsonb_array_elements(p_scenarios) as entries(item)
        group by lower(entries.item->>'id')
        having count(*) > 1
    ) then
        raise exception using errcode = '22023', message = 'Named scenario IDs must be unique.';
    end if;
    if exists (
        select translate(entries.item->>'name', 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz')
        from jsonb_array_elements(p_scenarios) as entries(item)
        group by translate(entries.item->>'name', 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz')
        having count(*) > 1
    ) then
        raise exception using errcode = '22023', message = 'Named scenario names must be unique.';
    end if;
end;
$$;

create or replace function public.finance_validate_inputs(p_inputs jsonb, p_cash_bills jsonb)
returns void
language plpgsql set search_path = ''
as $$
declare
    item jsonb;
    history_start date;
    history_end date;
    aggregate_market_value_cents numeric := 0;
    aggregate_cost_basis_cents numeric := 0;
begin
    if p_inputs is null
        or jsonb_typeof(p_inputs) is distinct from 'object'
        or octet_length(p_inputs::text) > 4000000
        or not public.finance_object_has_only_keys(
            p_inputs,
            array[
                'mode', 'income_events', 'event_rules', 'transactions', 'history_start', 'history_end',
                'history_complete', 'assumptions', 'credit_accounts', 'holdings', 'portfolio_returns',
                'policy', 'scenarios', 'alerts'
            ]
        )
        or jsonb_typeof(p_inputs->'mode') is distinct from 'string'
        or p_inputs->>'mode' not in ('scheduled', 'assumptions', 'history')
        or not public.finance_is_json_array(p_inputs->'income_events', 0, 200)
        or not public.finance_is_json_array(p_inputs->'event_rules', 0, 400)
        or not public.finance_is_json_array(p_inputs->'transactions', 0, 20000)
        or (
            jsonb_typeof(p_inputs->'history_start') is distinct from 'string'
            and jsonb_typeof(p_inputs->'history_start') is distinct from 'null'
        )
        or (
            jsonb_typeof(p_inputs->'history_end') is distinct from 'string'
            and jsonb_typeof(p_inputs->'history_end') is distinct from 'null'
        )
        or (
            jsonb_typeof(p_inputs->'history_start') = 'string'
            and not public.finance_is_valid_date(p_inputs->>'history_start')
        )
        or (
            jsonb_typeof(p_inputs->'history_end') = 'string'
            and not public.finance_is_valid_date(p_inputs->>'history_end')
        )
        or not public.finance_is_json_boolean(p_inputs->'history_complete')
        or not public.finance_is_json_array(p_inputs->'credit_accounts', 0, 100)
        or not public.finance_is_json_array(p_inputs->'holdings', 0, 500)
        or not public.finance_is_json_array(p_inputs->'portfolio_returns', 0, 20000)
        or not public.finance_is_json_array(p_inputs->'scenarios', 0, 20)
        or not public.finance_object_has_only_keys(
            p_inputs->'alerts',
            array['enabled', 'shortfall_probability', 'stale_after_days']
        )
        or not public.finance_is_json_boolean(p_inputs->'alerts'->'enabled')
        or not public.finance_is_json_number(p_inputs->'alerts'->'shortfall_probability', 0, 1)
        or not public.finance_is_json_integer(p_inputs->'alerts'->'stale_after_days', 1, 3650) then
        raise exception using errcode = '22023', message = 'Invalid supplemental finance inputs.';
    end if;

    if (jsonb_typeof(p_inputs->'history_start') = 'null') <> (jsonb_typeof(p_inputs->'history_end') = 'null') then
        raise exception using errcode = '22023', message = 'History start and end dates must be saved together.';
    end if;
    if jsonb_typeof(p_inputs->'history_start') = 'string' then
        history_start := (p_inputs->>'history_start')::date;
        history_end := (p_inputs->>'history_end')::date;
        if history_start > history_end then
            raise exception using errcode = '22023', message = 'History start cannot be after history end.';
        end if;
    elsif p_inputs->>'history_complete' = 'true' then
        raise exception using errcode = '22023', message = 'Complete history requires start and end dates.';
    end if;

    perform public.finance_validate_cash_bill_array(p_inputs->'income_events', 'Income event');
    for item in select value from jsonb_array_elements(p_inputs->'transactions') loop
        perform public.finance_validate_history_transaction(item);
        if history_start is not null and (
            (item->>'date')::date < history_start or (item->>'date')::date > history_end
        ) then
            raise exception using errcode = '22023', message = 'Historical transactions must fall inside history coverage.';
        end if;
    end loop;
    if exists (
        select lower(entries.item->>'id')
        from jsonb_array_elements(p_inputs->'transactions') as entries(item)
        group by lower(entries.item->>'id')
        having count(*) > 1
    ) then
        raise exception using errcode = '22023', message = 'Historical transaction IDs must be unique.';
    end if;

    perform public.finance_validate_assumptions(p_inputs->'assumptions');
    perform public.finance_validate_event_rules(
        p_inputs->'event_rules',
        p_cash_bills,
        p_inputs->'income_events'
    );

    for item in select value from jsonb_array_elements(p_inputs->'credit_accounts') loop
        perform public.finance_validate_credit_account(item);
    end loop;
    if exists (
        select lower(entries.item->>'id')
        from jsonb_array_elements(p_inputs->'credit_accounts') as entries(item)
        group by lower(entries.item->>'id')
        having count(*) > 1
    ) then
        raise exception using errcode = '22023', message = 'Credit account IDs must be unique.';
    end if;

    for item in select value from jsonb_array_elements(p_inputs->'holdings') loop
        perform public.finance_validate_holding(item);
    end loop;
    select
        coalesce(
            sum(
                (lots.lot->>'quantity')::numeric
                * (holdings.item->>'current_price_cents')::numeric
            ),
            0
        ),
        coalesce(
            sum(
                (lots.lot->>'quantity')::numeric
                * (lots.lot->>'cost_basis_per_share_cents')::numeric
            ),
            0
        )
    into aggregate_market_value_cents, aggregate_cost_basis_cents
    from jsonb_array_elements(p_inputs->'holdings') as holdings(item)
    cross join lateral jsonb_array_elements(holdings.item->'tax_lots') as lots(lot);
    if aggregate_market_value_cents > 100000000000
        or aggregate_cost_basis_cents > 100000000000 then
        raise exception using errcode = '22023', message = 'Aggregate holding value is too large.';
    end if;

    if exists (
        select lower(entries.item->>'id')
        from jsonb_array_elements(p_inputs->'holdings') as entries(item)
        group by lower(entries.item->>'id')
        having count(*) > 1
    ) then
        raise exception using errcode = '22023', message = 'Holding IDs must be unique.';
    end if;
    if exists (
        select lower(lots.lot->>'id')
        from jsonb_array_elements(p_inputs->'holdings') as holdings(item)
        cross join lateral jsonb_array_elements(holdings.item->'tax_lots') as lots(lot)
        group by lower(lots.lot->>'id')
        having count(*) > 1
    ) then
        raise exception using errcode = '22023', message = 'Tax-lot IDs must be unique across holdings.';
    end if;

    for item in select value from jsonb_array_elements(p_inputs->'portfolio_returns') loop
        if not public.finance_object_has_only_keys(item, array['date', 'return_decimal'])
            or jsonb_typeof(item->'date') is distinct from 'string'
            or not public.finance_is_valid_date(item->>'date')
            or not public.finance_is_json_number(item->'return_decimal', -1, 100) then
            raise exception using errcode = '22023', message = 'Invalid portfolio return fields.';
        end if;
    end loop;
    if exists (
        select entries.item->>'date'
        from jsonb_array_elements(p_inputs->'portfolio_returns') as entries(item)
        group by entries.item->>'date'
        having count(*) > 1
    ) then
        raise exception using errcode = '22023', message = 'Portfolio return dates cannot repeat.';
    end if;

    perform public.finance_validate_policy(p_inputs->'policy');
    perform public.finance_validate_scenarios(
        p_inputs->'scenarios',
        p_cash_bills,
        p_inputs->'income_events',
        p_inputs->'event_rules'
    );
end;
$$;

-- A pristine or cash-only workspace has no financial_inputs row. The default is
-- intentionally scheduled mode with empty collections, never generated income,
-- history, credit, or investments.
create or replace function public.default_finance_inputs()
returns jsonb
language sql immutable security definer set search_path = ''
as $$
    select '{
        "mode": "scheduled",
        "income_events": [],
        "event_rules": [],
        "transactions": [],
        "history_start": null,
        "history_end": null,
        "history_complete": false,
        "assumptions": {
            "monthly_variable_income_cents": 0,
            "monthly_essential_spending_cents": 0,
            "monthly_discretionary_spending_cents": 0,
            "income_variability_pct": 0,
            "spending_variability_pct": 0,
            "persistence_days": 7,
            "income_spending_correlation": 0,
            "market_assumptions_enabled": false,
            "expected_annual_return_pct": 0,
            "annual_return_volatility_pct": 0,
            "income_market_correlation": 0
        },
        "credit_accounts": [],
        "holdings": [],
        "portfolio_returns": [],
        "policy": {
            "operating_buffer_cents": 0,
            "coverage_target": 0.95,
            "max_credit_utilization": 0.30,
            "priorities": [
                "avoid_interest_bearing_debt",
                "minimize_taxable_sales",
                "minimize_deferred_spending"
            ],
            "settlement_days": 1,
            "external_transfer_days": 2,
            "capital_gains_rate": 0.15,
            "overdraft_apr": 0.18,
            "buffer_tolerance_dollar_days": null,
            "lot_selection": "fifo"
        },
        "scenarios": [],
        "alerts": {
            "enabled": true,
            "shortfall_probability": 0.05,
            "stale_after_days": 30
        }
    }'::jsonb;
$$;

create or replace function public.get_finance_workspace()
returns jsonb
language plpgsql stable security definer set search_path = ''
as $$
declare
    owner_id uuid := auth.uid();
    cash_snapshot jsonb;
    saved_inputs jsonb;
begin
    if owner_id is null then
        raise exception using errcode = '42501', message = 'Authentication required.';
    end if;

    -- Both save entry points update this record and cash in one transaction.
    select public.get_cash_workspace() into cash_snapshot;
    select inputs into saved_inputs
    from public.financial_inputs
    where user_id = owner_id;
    return cash_snapshot || jsonb_build_object(
        'inputs', coalesce(saved_inputs, public.default_finance_inputs())
    );
end;
$$;

-- The old cash primitive does not understand supplemental event references.
-- Keep its locking implementation private; neither RPC may bypass validation.
alter function public.save_cash_workspace(bigint, date, jsonb, jsonb)
    rename to finance_persist_cash_workspace;
revoke all on function public.finance_persist_cash_workspace(bigint, date, jsonb, jsonb)
    from public, anon, authenticated;

create or replace function public.save_finance_workspace(
    p_expected_revision bigint,
    p_as_of date,
    p_accounts jsonb,
    p_bills jsonb,
    p_inputs jsonb
)
returns jsonb
language plpgsql security definer set search_path = ''
as $$
declare
    owner_id uuid := auth.uid();
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

    perform public.finance_validate_cash_snapshot(p_accounts, p_bills);
    perform public.finance_validate_inputs(p_inputs, p_bills);

    -- Validation above covers both the replacement cash and supplemental data.
    perform public.finance_persist_cash_workspace(p_expected_revision, p_as_of, p_accounts, p_bills);

    insert into public.financial_inputs (user_id, inputs)
    values (owner_id, p_inputs)
    on conflict (user_id) do update
        set inputs = excluded.inputs,
            updated_at = now();

    return public.get_finance_workspace();
end;
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
    saved_inputs jsonb;
begin
    if owner_id is null then
        raise exception using errcode = '42501', message = 'Authentication required.';
    end if;
    select inputs into saved_inputs
    from public.financial_inputs
    where user_id = owner_id;

    -- Preserve supplemental data, but reject cash edits that would invalidate
    -- its event rules or named scenarios. A full save can change both together.
    perform public.save_finance_workspace(
        p_expected_revision, p_as_of, p_accounts, p_bills,
        coalesce(saved_inputs, public.default_finance_inputs())
    );
    return public.get_cash_workspace();
end;
$$;

-- RPC entry points are callable only by authenticated JWT sessions. Helpers are
-- intentionally not callable through PostgREST, even though they are required
-- internally by the security-definer entry points.
revoke all on function public.finance_is_valid_date(text) from public, anon, authenticated;
revoke all on function public.finance_object_has_only_keys(jsonb, text[]) from public, anon, authenticated;
revoke all on function public.finance_is_json_string(jsonb, integer, integer) from public, anon, authenticated;
revoke all on function public.finance_is_json_uuid(jsonb) from public, anon, authenticated;
revoke all on function public.finance_is_json_integer(jsonb, numeric, numeric) from public, anon, authenticated;
revoke all on function public.finance_is_json_number(jsonb, numeric, numeric) from public, anon, authenticated;
revoke all on function public.finance_is_json_number_above(jsonb, numeric, numeric) from public, anon, authenticated;
revoke all on function public.finance_is_json_boolean(jsonb) from public, anon, authenticated;
revoke all on function public.finance_is_rule_occurrence(date, text, date) from public, anon, authenticated;
revoke all on function public.finance_is_json_array(jsonb, integer, integer) from public, anon, authenticated;
revoke all on function public.finance_validate_cash_account(jsonb) from public, anon, authenticated;
revoke all on function public.finance_validate_cash_bill(jsonb) from public, anon, authenticated;
revoke all on function public.finance_validate_cash_snapshot(jsonb, jsonb) from public, anon, authenticated;
revoke all on function public.finance_validate_cash_bill_array(jsonb, text) from public, anon, authenticated;
revoke all on function public.finance_validate_assumptions(jsonb) from public, anon, authenticated;
revoke all on function public.finance_validate_history_transaction(jsonb) from public, anon, authenticated;
revoke all on function public.finance_validate_credit_account(jsonb) from public, anon, authenticated;
revoke all on function public.finance_validate_holding(jsonb) from public, anon, authenticated;
revoke all on function public.finance_validate_policy(jsonb) from public, anon, authenticated;
revoke all on function public.finance_validate_event_rules(jsonb, jsonb, jsonb) from public, anon, authenticated;
revoke all on function public.finance_validate_scenarios(jsonb, jsonb, jsonb, jsonb) from public, anon, authenticated;
revoke all on function public.finance_validate_inputs(jsonb, jsonb) from public, anon, authenticated;
revoke all on function public.default_finance_inputs() from public, anon, authenticated;
revoke all on function public.get_finance_workspace() from public, anon;
revoke all on function public.save_finance_workspace(bigint, date, jsonb, jsonb, jsonb) from public, anon;
revoke all on function public.save_cash_workspace(bigint, date, jsonb, jsonb) from public, anon;
grant execute on function public.get_finance_workspace() to authenticated;
grant execute on function public.save_finance_workspace(bigint, date, jsonb, jsonb, jsonb) to authenticated;
grant execute on function public.save_cash_workspace(bigint, date, jsonb, jsonb) to authenticated;
