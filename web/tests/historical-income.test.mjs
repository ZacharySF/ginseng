import assert from 'node:assert/strict';
import { after, test } from 'node:test';
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import ts from 'typescript';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const temporary = await mkdtemp(join(tmpdir(), 'ginseng-history-income-test-'));
after(() => rm(temporary, { recursive: true, force: true }));
const source = ts.transpileModule(
	await readFile(join(root, 'src/lib/historical-income.ts'), 'utf8'),
	{ compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }
).outputText;
await writeFile(join(temporary, 'historical-income.mjs'), source);
const { deriveHistoricalIncome } = await import(
	pathToFileURL(join(temporary, 'historical-income.mjs')).href
);

function income(id, date, amount_cents, category = 'income_variable') {
	return { id, date, amount_cents, category, description: id, source_key: null };
}

test('uses only complete calendar months and derives monthly coefficient of variation', () => {
	const result = deriveHistoricalIncome(
		[
			income('partial-start', '2026-01-20', 900_000),
			income('february', '2026-02-10', 100_000),
			income('march', '2026-03-10', 300_000),
			income('partial-end', '2026-04-10', 900_000)
		],
		'2026-01-15',
		'2026-04-20',
		12
	);
	assert.equal(result.status, 'ready');
	assert.equal(result.monthlyIncomeCents, 200_000);
	assert.equal(result.variability, 0.5);
	assert.equal(result.months, 2);
	assert.equal(result.periodStart, '2026-02-01');
	assert.equal(result.periodEnd, '2026-03-31');
});

test('keeps zero-income months and excludes fixed income from the estimate', () => {
	const result = deriveHistoricalIncome(
		[
			income('january', '2026-01-10', 100_000),
			income('fixed-february', '2026-02-10', 500_000, 'income_fixed'),
			income('march', '2026-03-10', 100_000)
		],
		'2026-01-01',
		'2026-03-31',
		'all'
	);
	assert.equal(result.status, 'ready');
	assert.equal(result.monthlyIncomeCents, 66_667);
	assert.ok(Math.abs(result.variability - Math.SQRT1_2) < 1e-12);
});

test('uses the requested trailing complete months and caps the stored variability', () => {
	const result = deriveHistoricalIncome(
		[income('june', '2026-06-10', 600_000)],
		'2026-01-01',
		'2026-06-30',
		12
	);
	assert.equal(result.status, 'ready');
	assert.equal(result.months, 6);
	assert.equal(result.variability, 2);
	assert.ok(result.uncappedVariability > 2);
});

test('requires enough valid coverage and at least one variable-income observation', () => {
	assert.equal(
		deriveHistoricalIncome([], '2026-01-02', '2026-03-30', 12).reason,
		'duration'
	);
	assert.equal(
		deriveHistoricalIncome([], '2026-01-01', '2026-03-31', 12).reason,
		'income'
	);
});
