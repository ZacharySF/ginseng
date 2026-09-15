-- Run against an isolated local stack after migration 0005.
begin;
create extension if not exists pgtap with schema extensions;
set local search_path = public, extensions;
select plan(23);

select is(public.default_finance_inputs()->>'roth_contribution_basis_cents', '0',
    'Missing Roth contribution records do not unlock earnings');
select is(public.default_finance_inputs()->'assumptions'->>'income_payments_per_month', '2',
    'Payment frequency has an explicit default');
select lives_ok($sql$
    select public.finance_validate_inputs(
        (public.default_finance_inputs() - 'roth_contribution_basis_cents') #- '{assumptions,income_payments_per_month}', '[]')
$sql$, 'Previously saved inputs remain valid');

create temporary table wrapper_fixture as select
    '{"id":"50000000-0000-4000-8000-000000000001","symbol":"FUND","account":"taxable","current_price_cents":10000,"tax_lots":[]}'::jsonb as holding;
select lives_ok('select public.finance_validate_holding(holding) from wrapper_fixture', 'Taxable holdings remain valid');
select lives_ok($sql$ select public.finance_validate_holding(jsonb_set(holding, '{account}', '"traditional"')) from wrapper_fixture $sql$, 'Traditional IRA holdings persist');
select lives_ok($sql$ select public.finance_validate_holding(jsonb_set(holding, '{account}', '"roth"')) from wrapper_fixture $sql$, 'Roth IRA holdings persist');
select lives_ok($sql$ select public.finance_validate_holding(jsonb_set(holding, '{account}', '"retirement"')) from wrapper_fixture $sql$, 'Legacy unclassified retirement remains readable');
select throws_ok($sql$ select public.finance_validate_holding(jsonb_set(holding, '{account}', '"unknown"')) from wrapper_fixture $sql$, '22023', null, 'Unknown wrappers are rejected');
select throws_ok($sql$ select public.finance_validate_inputs(jsonb_set(public.default_finance_inputs(), '{roth_contribution_basis_cents}', '-1'), '[]') $sql$, '22023', null, 'Negative Roth contribution basis is rejected');
select throws_ok($sql$ select public.finance_validate_inputs(jsonb_set(public.default_finance_inputs(), '{roth_contribution_basis_cents}', 'null'), '[]') $sql$, '22023', null, 'Explicit null contribution basis is rejected');
select throws_ok($sql$ select public.finance_validate_assumptions(jsonb_set(public.default_finance_inputs()->'assumptions', '{income_payments_per_month}', '0')) $sql$, '22023', null, 'Zero payment frequency is rejected');
select throws_ok($sql$ select public.finance_validate_assumptions(jsonb_set(public.default_finance_inputs()->'assumptions', '{income_payments_per_month}', 'null')) $sql$, '22023', null, 'Explicit null payment frequency is rejected');
select throws_ok($sql$ select public.finance_validate_assumptions(jsonb_set(public.default_finance_inputs()->'assumptions', '{income_payments_per_month}', '31')) $sql$, '22023', null, 'Out-of-range frequency is rejected');

create temporary table credit_fixture as select
    '{"id":"50000000-0000-4000-8000-000000000002","name":"Card","credit_limit_cents":100000,"current_balance_cents":0,"purchase_apr":0.2,"statement_close_day":20,"payment_due_day":18,"grace_period_eligible":false,"minimum_payment_cents":1000}'::jsonb as card;
select lives_ok('select public.finance_validate_credit_account(card) from credit_fixture', 'Legacy cards without advance terms remain valid');
select lives_ok($sql$ select public.finance_validate_credit_account(card || '{"cash_advance_limit_cents":20000,"cash_advance_apr":0.3,"cash_advance_fee_pct":0.05}') from credit_fixture $sql$, 'Explicit cash advance terms persist');
select throws_ok($sql$ select public.finance_validate_credit_account(card || '{"cash_advance_limit_cents":-1}') from credit_fixture $sql$, '22023', null, 'Negative cash advance capacity is rejected');
select throws_ok($sql$ select public.finance_validate_credit_account(card || '{"cash_advance_apr":null}') from credit_fixture $sql$, '22023', null, 'Explicit null cash advance APR is rejected');
select throws_ok($sql$ select public.finance_validate_credit_account(card || '{"cash_advance_fee_pct":0.51}') from credit_fixture $sql$, '22023', null, 'Out-of-range advance fee is rejected');
insert into auth.users(id, email) values
    ('50000000-0000-4000-8000-000000000010', 'unified-funding-owner@example.test');
set local role authenticated;
select set_config('request.jwt.claim.sub', '50000000-0000-4000-8000-000000000010', true);
select is(public.save_finance_workspace(
    0, '2026-09-13',
    '[{"id":"50000000-0000-4000-8000-000000000011","name":"Checking","kind":"checking","balance_cents":300000}]', '[]',
    jsonb_set(public.get_finance_workspace()->'inputs', '{assumptions,income_payments_per_month}', '3.5') ||
    '{"roth_contribution_basis_cents":125000,"holdings":[
        {"id":"50000000-0000-4000-8000-000000000012","symbol":"IRA","account":"traditional","current_price_cents":10000,"tax_lots":[]},
        {"id":"50000000-0000-4000-8000-000000000013","symbol":"ROTH","account":"roth","current_price_cents":10000,"tax_lots":[]}
    ],"credit_accounts":[
        {"id":"50000000-0000-4000-8000-000000000014","name":"Card","credit_limit_cents":100000,"current_balance_cents":0,"purchase_apr":0.2,"statement_close_day":20,"payment_due_day":18,"grace_period_eligible":false,"minimum_payment_cents":1000,"cash_advance_limit_cents":20000,"cash_advance_apr":0.3,"cash_advance_fee_pct":0.05}
    ]}'::jsonb
)->>'revision', '1', 'Authenticated save accepts the combined funding inputs');
select is(jsonb_path_query_array(public.get_finance_workspace(), '$.inputs.holdings[*].account'), '["traditional","roth"]'::jsonb,
    'Withdrawal account types survive a workspace round trip');
select is(public.get_finance_workspace()->'inputs'->>'roth_contribution_basis_cents', '125000',
    'Remaining Roth contribution basis survives a workspace round trip');
select is(public.get_finance_workspace()->'inputs'->'credit_accounts'->0->>'cash_advance_fee_pct', '0.05',
    'Cash advance fees survive a workspace round trip');
select is(public.get_finance_workspace()->'inputs'->'assumptions'->>'income_payments_per_month', '3.5',
    'Fractional expected payment frequency survives a workspace round trip');
select * from finish();
rollback;
