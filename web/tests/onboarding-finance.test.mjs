import assert from 'node:assert/strict';
import { after, test } from 'node:test';
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import ts from 'typescript';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const temporary = await mkdtemp(join(tmpdir(), 'ginseng-onboarding-finance-test-'));
after(() => rm(temporary, { recursive: true, force: true }));
const source = ts.transpileModule(
	await readFile(join(root, 'src/lib/onboarding-finance.ts'), 'utf8'),
	{ compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }
).outputText;
await writeFile(join(temporary, 'onboarding-finance.mjs'), source);
const { cashStepError, scheduleStepError, ruleForEvent } = await import(
	pathToFileURL(join(temporary, 'onboarding-finance.mjs')).href
);

const account = { id: 'account-1', name: 'Checking', kind: 'checking', balance_cents: -2_500 };
const event = { id: 'event-1', label: 'Paycheck', amount_cents: 125_000, due_date: '2026-09-18' };

test('cash setup requires a valid opening date and one named account', () => {
	assert.equal(cashStepError(null, [account]), 'Choose the opening date for these balances.');
	assert.equal(cashStepError('2026-02-30', [account]), 'Choose the opening date for these balances.');
	assert.equal(cashStepError('2026-09-13', []), 'Add at least one checking or savings account.');
	assert.equal(cashStepError('2026-09-13', [{ ...account, name: '  ' }]), 'Name every cash account.');
	assert.equal(cashStepError('2026-09-13', [account]), null);
});

test('income and bill schedules may be empty but reject incomplete rows', () => {
	assert.equal(scheduleStepError('income', []), null);
	assert.equal(scheduleStepError('bill', []), null);
	assert.equal(scheduleStepError('income', [{ ...event, amount_cents: 0 }]), 'Enter an amount greater than zero for every income.');
	assert.equal(scheduleStepError('bill', [{ ...event, due_date: 'bad-date' }]), 'Choose a valid first date for every bill.');
	assert.equal(scheduleStepError('income', [event]), null);
});

test('event rules are matched only to their event identifier', () => {
	const rules = [
		{ event_id: 'other', recurrence: 'none', end_date: null, settlements: [] },
		{ event_id: 'event-1', recurrence: 'monthly', end_date: null, settlements: [] }
	];
	assert.equal(ruleForEvent(rules, 'event-1')?.recurrence, 'monthly');
	assert.equal(ruleForEvent(rules, 'missing'), undefined);
});
