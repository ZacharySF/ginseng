-- Run only against the isolated local stack: supabase test db.
-- Every fixture and mutation rolls back; never run tests against production.
begin;
create extension if not exists pgtap with schema extensions;
set local search_path = public, extensions;
select plan(20);

insert into auth.users(id, email) values
    ('10000000-0000-4000-8000-000000000001', 'cash-owner-a@example.test'),
    ('10000000-0000-4000-8000-000000000002', 'cash-owner-b@example.test');

set local role anon;
select throws_ok('select public.get_cash_workspace()', '42501', null,
    'Anonymous callers cannot read snapshots');
select throws_ok($sql$select public.save_cash_workspace(0, '2026-09-11', '[]', '[]')$sql$,
    '42501', null, 'Anonymous callers cannot save snapshots');

set local role authenticated;
select set_config('request.jwt.claim.sub', '10000000-0000-4000-8000-000000000001', true);
select is(public.get_cash_workspace()->>'revision', '0', 'New owner has no saved revision');
select is(public.save_cash_workspace(0, '2026-09-11',
    '[{"id":"20000000-0000-4000-8000-000000000001","name":"Checking","kind":"checking","balance_cents":10001}]',
    '[{"id":"30000000-0000-4000-8000-000000000001","label":"Rent","amount_cents":3000,"due_date":"2026-09-12"}]'
)->>'revision', '1', 'First save creates a committed revision');
select is(public.get_cash_workspace()->'accounts'->0->>'balance_cents', '10001',
    'Reload preserves exact cents');
select throws_ok($sql$insert into public.cash_accounts(user_id,id,name,kind,balance_cents)
    values ('10000000-0000-4000-8000-000000000001','20000000-0000-4000-8000-000000000002','Bypass','checking',42)$sql$,
    '42501', null, 'Direct insert cannot bypass revision control');
select throws_ok($sql$update public.cash_accounts set balance_cents=0$sql$,
    '42501', null, 'Direct update cannot bypass revision control');
select throws_ok($sql$delete from public.cash_bills$sql$,
    '42501', null, 'Direct delete cannot bypass revision control');

select set_config('request.jwt.claim.sub', '10000000-0000-4000-8000-000000000002', true);
select is((select count(*)::integer from public.cash_accounts), 0,
    'Other owner cannot read accounts through the table API');
select is((select count(*)::integer from public.cash_bills), 0,
    'Other owner cannot read bills through the table API');
select is(public.get_cash_workspace()->>'revision', '0', 'Other owner has an independent empty snapshot');
select is(public.save_cash_workspace(0, '2026-09-11',
    '[{"id":"20000000-0000-4000-8000-000000000001","name":"Other checking","kind":"checking","balance_cents":777}]',
    '[]')->>'revision', '1', 'Same record ID in another workspace cannot replace the first owner');
select throws_ok($sql$select public.save_cash_workspace(0,'2026-09-11','[]','[]')$sql$,
    '40001', null, 'Stale initial save conflicts instead of overwriting');

select set_config('request.jwt.claim.sub', '10000000-0000-4000-8000-000000000001', true);
select is(public.get_cash_workspace()->'accounts'->0->>'balance_cents', '10001',
    'Other owner save left original account untouched');
select throws_ok($sql$select public.save_cash_workspace(1,'2026-09-11',
    '[{"id":"20000000-0000-4000-8000-000000000001","name":"Changed","kind":"checking","balance_cents":1.5}]','[]')$sql$,
    '22023', null, 'Fractional cents are rejected at the database boundary');
select throws_ok($sql$select public.save_cash_workspace(1,'2026-09-11',
    '[{"id":"20000000-0000-4000-8000-000000000001","name":"Changed","kind":"checking","balance_cents":999}]',
    '[{"id":"30000000-0000-4000-8000-000000000001","label":"Invalid","amount_cents":0,"due_date":"2026-09-12"}]')$sql$,
    '23514', null, 'Invalid bill rolls back the whole replacement');
select is(public.get_cash_workspace()->'accounts'->0->>'balance_cents', '10001',
    'Failed replacement retains prior account data');
select is(public.get_cash_workspace()->>'revision', '1', 'Failed replacement does not advance revision');
select is(public.save_cash_workspace(1, '2026-09-11',
    '[{"id":"20000000-0000-4000-8000-000000000001","name":"Checking","kind":"checking","balance_cents":10001}]',
    '[]')->'bills', '[]'::jsonb, 'Owner can deliberately remove their saved bill');

select set_config('request.jwt.claim.sub', '10000000-0000-4000-8000-000000000002', true);
select is(public.get_cash_workspace()->'accounts'->0->>'balance_cents', '777',
    'Owner replacement leaves other workspace untouched');

reset role;
select * from finish();
rollback;
