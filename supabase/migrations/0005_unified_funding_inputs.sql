-- Add account wrappers and explicit payment/cash-advance assumptions.
-- Existing snapshots remain valid; omitted fields receive conservative defaults.
-- CREATE OR REPLACE preserves existing helper execution restrictions.

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
            'annual_return_volatility_pct', 'income_market_correlation', 'income_payments_per_month'
        ]
    )
        or not public.finance_is_json_integer(p_assumptions->'monthly_variable_income_cents', 0, 100000000000)
        or not public.finance_is_json_integer(p_assumptions->'monthly_essential_spending_cents', 0, 100000000000)
        or not public.finance_is_json_integer(p_assumptions->'monthly_discretionary_spending_cents', 0, 100000000000)
        or not public.finance_is_json_number_above(coalesce(p_assumptions->'income_payments_per_month', '2'::jsonb), 0, 30)
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

create or replace function public.finance_validate_credit_account(p_credit jsonb)
returns void
language plpgsql set search_path = ''
as $$
begin
    if not public.finance_object_has_only_keys(
        p_credit,
        array[
            'id', 'name', 'credit_limit_cents', 'current_balance_cents', 'purchase_apr',
            'statement_close_day', 'payment_due_day', 'grace_period_eligible', 'minimum_payment_cents',
            'cash_advance_limit_cents', 'cash_advance_apr', 'cash_advance_fee_pct'
        ]
    )
        or not public.finance_is_json_integer(coalesce(p_credit->'cash_advance_limit_cents', '0'::jsonb), 0, 100000000000)
        or not public.finance_is_json_number(coalesce(p_credit->'cash_advance_apr', '0'::jsonb), 0, 1)
        or not public.finance_is_json_number(coalesce(p_credit->'cash_advance_fee_pct', '0'::jsonb), 0, 0.5)
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
        or p_holding->>'account' not in ('taxable', 'traditional', 'roth', 'retirement')
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
                'policy', 'scenarios', 'alerts', 'roth_contribution_basis_cents'
            ]
        )
        or not public.finance_is_json_integer(coalesce(p_inputs->'roth_contribution_basis_cents', '0'::jsonb), 0, 100000000000)
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

create or replace function public.default_finance_inputs()
returns jsonb
language sql immutable security definer set search_path = ''
as $$
    select '{
        "mode": "scheduled",
        "roth_contribution_basis_cents": 0,
        "income_events": [],
        "event_rules": [],
        "transactions": [],
        "history_start": null,
        "history_end": null,
        "history_complete": false,
        "assumptions": {
            "monthly_variable_income_cents": 0,
            "income_payments_per_month": 2,
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
