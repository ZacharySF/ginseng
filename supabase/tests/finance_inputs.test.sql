-- Canonical finance persistence, ownership, and CAS behavior.
-- Run only through `supabase test db` against an isolated local stack.

begin;
create extension if not exists pgtap with schema extensions;
set local search_path = public, extensions;
select plan(39);

insert into auth.users(id, email) values
    ('40000000-0000-4000-8000-000000000001', 'finance-owner-a@example.test'),
    ('40000000-0000-4000-8000-000000000002', 'finance-owner-b@example.test');

set local role anon;
select throws_ok('select public.get_finance_workspace()', '42501', null,
    'Anonymous callers cannot read finance snapshots');
select throws_ok($sql$
    select public.save_finance_workspace(0, '2026-09-11', '[]', '[]', '{}'::jsonb)
$sql$, '42501', null, 'Anonymous callers cannot save finance snapshots');

set local role authenticated;
select set_config('request.jwt.claim.sub', '40000000-0000-4000-8000-000000000001', true);
select is(public.get_finance_workspace()->>'revision', '0',
    'A pristine owner receives the existing empty cash revision');
select is(public.get_finance_workspace()->'inputs'->>'mode', 'scheduled',
    'A pristine owner receives scheduled inputs, not a generated model');
select is(public.get_finance_workspace()->'inputs'->'income_events', '[]'::jsonb,
    'A pristine owner receives no synthetic income events');

select is(public.save_cash_workspace(0, '2026-09-11',
    '[{"id":"40000000-0000-4000-8000-000000000010","name":"Checking","kind":"checking","balance_cents":10001}]',
    '[{"id":"40000000-0000-4000-8000-000000000011","label":"Rent","amount_cents":3000,"due_date":"2026-10-01"}]'
)->>'revision', '1', 'Existing cash writer creates the first cash revision');

select is(public.save_finance_workspace(
    1,
    '2026-09-11',
    '[{"id":"40000000-0000-4000-8000-000000000010","name":"Checking","kind":"checking","balance_cents":10001}]',
    '[{"id":"40000000-0000-4000-8000-000000000011","label":"Rent","amount_cents":3000,"due_date":"2026-10-01"}]',
    jsonb_set(
        jsonb_set(
            public.get_finance_workspace()->'inputs',
            '{income_events}',
            '[{"id":"40000000-0000-4000-8000-000000000012","label":"Salary","amount_cents":250000,"due_date":"2026-09-15"}]'::jsonb
        ),
        '{event_rules}',
        '[{"event_id":"40000000-0000-4000-8000-000000000012","recurrence":"monthly","end_date":null,"settlements":[]},{"event_id":"40000000-0000-4000-8000-000000000011","recurrence":"monthly","end_date":null,"settlements":[]}]'::jsonb
    )
)->>'revision', '2', 'Full finance save advances the existing cash revision');
select is(public.get_finance_workspace()->'inputs'->'income_events'->0->>'label', 'Salary',
    'Full finance save returns the canonical supplemental input record');

select is(public.save_cash_workspace(2, '2026-09-11',
    '[{"id":"40000000-0000-4000-8000-000000000010","name":"Checking","kind":"checking","balance_cents":10001}]',
    '[{"id":"40000000-0000-4000-8000-000000000011","label":"Rent","amount_cents":3000,"due_date":"2026-10-01"}]'
)->>'revision', '3', 'Existing cash-only save remains usable after a finance save');
select is(public.get_finance_workspace()->'inputs'->'income_events'->0->>'label', 'Salary',
    'Cash-only save leaves supplemental income intact');

select throws_ok($sql$
    select public.save_cash_workspace(
        3, '2026-09-11',
        jsonb_set(public.get_cash_workspace()->'accounts', '{0,name}', to_jsonb(U&'Checking\00A0'::text)),
        public.get_cash_workspace()->'bills'
    )
$sql$, '22023', null, 'Cash RPC rejects edge Unicode whitespace that canonical readers reject');
select throws_ok($sql$
    select public.save_finance_workspace(
        3, '2026-09-11', public.get_cash_workspace()->'accounts', public.get_cash_workspace()->'bills',
        jsonb_set(public.get_finance_workspace()->'inputs', '{scenarios}',
            jsonb_build_array(jsonb_build_object(
                'id', '40000000-0000-4000-8000-000000000020',
                'name', U&'Night\2028', 'base_revision', 3, 'overrides', '{}'::jsonb
            ))
        )
    )
$sql$, '22023', null, 'Scenario names cannot end with Unicode line separators');

select throws_ok($sql$
    select public.save_cash_workspace(
        3, '2026-09-11', public.get_cash_workspace()->'accounts', '[]'
    )
$sql$, '22023', null, 'Cash-only saves cannot orphan a saved recurring bill');
select throws_ok($sql$
    select public.finance_persist_cash_workspace(
        3, '2026-09-11', public.get_cash_workspace()->'accounts', '[]'
    )
$sql$, '42501', null, 'Authenticated callers cannot bypass complete-workspace validation');

select throws_ok($sql$
    select public.save_finance_workspace(
        3,
        '2026-09-11',
        '[{"id":"40000000-0000-4000-8000-000000000010","name":"Checking","kind":"checking","balance_cents":99999}]',
        '[{"id":"40000000-0000-4000-8000-000000000011","label":"Rent","amount_cents":3000,"due_date":"2026-10-01"}]',
        jsonb_set(
            public.get_finance_workspace()->'inputs',
            '{transactions}',
            '[{"id":"40000000-0000-4000-8000-000000000013","date":"2026-09-10","description":"Wrong-way expense","amount_cents":25,"category":"expense_fixed","source_key":null}]'::jsonb
        )
    )
$sql$, '22023', null, 'Invalid historical transaction units reject the complete finance save');
select is(public.get_finance_workspace()->'accounts'->0->>'balance_cents', '10001',
    'Invalid full save rolls back the proposed cash replacement');
select is(public.get_finance_workspace()->'revision', '3',
    'Invalid full save does not advance the shared cash revision');
select is(public.get_finance_workspace()->'inputs'->'income_events'->0->>'label', 'Salary',
    'Invalid full save does not replace supplemental inputs');

select throws_ok($sql$
    select public.save_finance_workspace(
        2,
        '2026-09-11',
        '[{"id":"40000000-0000-4000-8000-000000000010","name":"Checking","kind":"checking","balance_cents":10001}]',
        '[{"id":"40000000-0000-4000-8000-000000000011","label":"Rent","amount_cents":3000,"due_date":"2026-10-01"}]',
        jsonb_set(public.get_finance_workspace()->'inputs', '{assumptions,monthly_variable_income_cents}', '999'::jsonb)
    )
$sql$, '40001', null, 'Stale full finance save reports the established cash CAS conflict');
select is(public.get_finance_workspace()->'inputs'->'assumptions'->>'monthly_variable_income_cents', '0',
    'CAS conflict leaves supplemental inputs unchanged');

select throws_ok($sql$
    select public.save_finance_workspace(
        3,
        '2026-09-11',
        '[{"id":"40000000-0000-4000-8000-000000000010","name":"Checking","kind":"checking","balance_cents":10001}]',
        '[{"id":"40000000-0000-4000-8000-000000000011","label":"Rent","amount_cents":3000,"due_date":"2026-10-01"}]',
        jsonb_set(
            public.get_finance_workspace()->'inputs',
            '{income_events}',
            '[{"id":"40000000-0000-4000-8000-000000000011","label":"Duplicate event","amount_cents":1,"due_date":"2026-09-12"}]'::jsonb
        )
    )
$sql$, '22023', null, 'Cash-bill and income UUID collisions are rejected');
select throws_ok($sql$
    select public.save_finance_workspace(
        3,
        '2026-09-11',
        '[{"id":"40000000-0000-4000-8000-000000000010","name":"Checking","kind":"checking","balance_cents":10001}]',
        '[{"id":"40000000-0000-4000-8000-000000000011","label":"Rent","amount_cents":3000,"due_date":"2026-10-01"}]',
        jsonb_set(
            public.get_finance_workspace()->'inputs',
            '{event_rules}',
            '[{"event_id":"40000000-0000-4000-8000-000000000011","recurrence":"monthly","end_date":null,"settlements":[{"due_date":"2026-10-02","status":"settled","settled_on":"2026-10-02"}]}]'::jsonb
        )
    )
$sql$, '22023', null, 'Settlements must be real occurrences of their anchored event');
select throws_ok($sql$
    select public.save_finance_workspace(
        3,
        '2026-09-11',
        '[{"id":"40000000-0000-4000-8000-000000000010","name":"Checking","kind":"checking","balance_cents":10001}]',
        '[{"id":"40000000-0000-4000-8000-000000000011","label":"Rent","amount_cents":3000,"due_date":"2026-10-01"}]',
        jsonb_set(
            public.get_finance_workspace()->'inputs',
            '{credit_accounts}',
            '[{"id":"40000000-0000-4000-8000-000000000014","name":"Card","credit_limit_cents":10000,"current_balance_cents":500,"purchase_apr":1.1,"statement_close_day":10,"payment_due_day":20,"grace_period_eligible":true,"minimum_payment_cents":25}]'::jsonb
        )
    )
$sql$, '22023', null, 'Credit APR must remain a decimal rate');
select throws_ok($sql$
    select public.save_finance_workspace(
        3,
        '2026-09-11',
        '[{"id":"40000000-0000-4000-8000-000000000010","name":"Checking","kind":"checking","balance_cents":10001}]',
        '[{"id":"40000000-0000-4000-8000-000000000011","label":"Rent","amount_cents":3000,"due_date":"2026-10-01"}]',
        jsonb_set(
            public.get_finance_workspace()->'inputs',
            '{holdings}',
            '[{"id":"40000000-0000-4000-8000-000000000015","symbol":"ETF","account":"taxable","current_price_cents":5000,"tax_lots":[{"id":"40000000-0000-4000-8000-000000000016","quantity":0,"cost_basis_per_share_cents":4000,"purchase_date":"2026-01-01"}]}]'::jsonb
        )
    )
$sql$, '22023', null, 'Tax lots require a positive share quantity');
select throws_ok($sql$
    select public.save_finance_workspace(
        3,
        '2026-09-11',
        '[{"id":"40000000-0000-4000-8000-000000000010","name":"Checking","kind":"checking","balance_cents":10001}]',
        '[{"id":"40000000-0000-4000-8000-000000000011","label":"Rent","amount_cents":3000,"due_date":"2026-10-01"}]',
        jsonb_set(
            public.get_finance_workspace()->'inputs',
            '{holdings}',
            '[{"id":"40000000-0000-4000-8000-000000000015","symbol":"ETF","account":"taxable","current_price_cents":100000000000,"tax_lots":[{"id":"40000000-0000-4000-8000-000000000016","quantity":2,"cost_basis_per_share_cents":100000000000,"purchase_date":"2026-01-01"}]}]'::jsonb
        )
    )
$sql$, '22023', null, 'Holding aggregates cannot exceed the supported money range');
select throws_ok($sql$
    select public.save_finance_workspace(
        3,
        '2026-09-11',
        '[{"id":"40000000-0000-4000-8000-000000000010","name":"Checking","kind":"checking","balance_cents":10001}]',
        '[{"id":"40000000-0000-4000-8000-000000000011","label":"Rent","amount_cents":3000,"due_date":"2026-10-01"}]',
        jsonb_set(
            public.get_finance_workspace()->'inputs',
            '{scenarios}',
            '[
                {"id":"40000000-0000-4000-8000-000000000017","name":"More rent","base_revision":3,"overrides":{"mode":"scheduled"}},
                {"id":"40000000-0000-4000-8000-000000000018","name":"more rent","base_revision":3,"overrides":{"mode":"scheduled"}}
            ]'::jsonb
        )
    )
$sql$, '22023', null, 'Scenario names cannot collide case-insensitively');
select throws_ok($sql$
    select public.save_finance_workspace(
        3,
        '2026-09-11',
        '[{"id":"40000000-0000-4000-8000-000000000010","name":"Checking","kind":"checking","balance_cents":10001}]',
        '[{"id":"40000000-0000-4000-8000-000000000011","label":"Rent","amount_cents":3000,"due_date":"2026-10-01"}]',
        jsonb_set(
            public.get_finance_workspace()->'inputs',
            '{scenarios}',
            '[{"id":"40000000-0000-4000-8000-000000000017","name":"Broken event replacement","base_revision":3,"overrides":{"event_rules":[{"event_id":"40000000-0000-4000-8000-000000000099","recurrence":"none","end_date":null,"settlements":[]}]}}]'::jsonb
        )
    )
$sql$, '22023', null, 'Nested scenario rules must refer to effective cash-flow events');
select is(public.get_finance_workspace()->>'revision', '3',
    'Rejected supplemental schemas leave the shared revision unchanged');

select set_config('request.jwt.claim.sub', '40000000-0000-4000-8000-000000000002', true);
select is((select count(*)::integer from public.financial_inputs), 0,
    'A second owner cannot read another owner supplemental record through RLS');
select is(public.get_finance_workspace()->>'revision', '0',
    'A second owner receives an independent pristine finance workspace');
select throws_ok($sql$
    insert into public.financial_inputs(user_id, inputs)
    values ('40000000-0000-4000-8000-000000000002', '{}'::jsonb)
$sql$, '42501', null, 'Direct supplemental inserts cannot bypass the CAS RPC');
select throws_ok($sql$
    update public.financial_inputs set inputs = '{}'::jsonb
$sql$, '42501', null, 'Direct supplemental updates cannot bypass the CAS RPC');
select throws_ok($sql$
    delete from public.financial_inputs
$sql$, '42501', null, 'Direct supplemental deletes cannot bypass the CAS RPC');

select is(public.save_finance_workspace(
    0,
    '2026-09-11',
    '[{"id":"40000000-0000-4000-8000-000000000010","name":"Other checking","kind":"checking","balance_cents":777}]',
    '[]',
    jsonb_set(
        public.get_finance_workspace()->'inputs',
        '{credit_accounts}',
        '[{"id":"40000000-0000-4000-8000-000000000014","name":"Over-limit card","credit_limit_cents":500,"current_balance_cents":700,"purchase_apr":0.2,"statement_close_day":10,"payment_due_day":20,"grace_period_eligible":false,"minimum_payment_cents":25}]'::jsonb
    )
)->>'revision', '1', 'Over-limit credit balances persist as a real owner-specific snapshot');
select is(public.get_finance_workspace()->'inputs'->'credit_accounts'->0->>'current_balance_cents', '700',
    'An over-limit current balance is retained instead of being rejected or clamped');

select set_config('request.jwt.claim.sub', '40000000-0000-4000-8000-000000000001', true);
select is(public.get_finance_workspace()->'inputs'->'income_events'->0->>'label', 'Salary',
    'Other owner full save cannot overwrite the first owner inputs');
select is(public.get_finance_workspace()->'accounts'->0->>'balance_cents', '10001',
    'Other owner full save cannot overwrite the first owner cash snapshot');

select is(public.save_finance_workspace(
    3, '2026-09-11', public.get_cash_workspace()->'accounts', '[]',
    jsonb_set(
        public.get_finance_workspace()->'inputs', '{event_rules}',
        '[{"event_id":"40000000-0000-4000-8000-000000000012","recurrence":"monthly","end_date":null,"settlements":[]}]'::jsonb
    )
)->'bills', '[]'::jsonb, 'A full save can remove a bill and its recurring rule atomically');

select is(jsonb_path_query_array(public.save_finance_workspace(
    4, '2026-09-11', public.get_cash_workspace()->'accounts', '[]',
    jsonb_set(public.get_finance_workspace()->'inputs', '{scenarios}', '[
        {"id":"40000000-0000-4000-8000-000000000021","name":"Straße","base_revision":4,"overrides":{}},
        {"id":"40000000-0000-4000-8000-000000000022","name":"STRASSE","base_revision":4,"overrides":{}},
        {"id":"40000000-0000-4000-8000-000000000023","name":"ΟΣ","base_revision":4,"overrides":{}},
        {"id":"40000000-0000-4000-8000-000000000024","name":"ος","base_revision":4,"overrides":{}}
    ]'::jsonb)
), '$.inputs.scenarios[*].name'), '["Straße","STRASSE","ΟΣ","ος"]'::jsonb,
    'Distinct Unicode names remain readable without locale-dependent case folding');

reset role;
select * from finish();
rollback;
