import assert from 'node:assert/strict';
import { after, test } from 'node:test';
import { mkdtemp, readFile, rm, symlink, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { compile } from 'svelte/compiler';
import { render } from 'svelte/server';
import ts from 'typescript';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const temporary = await mkdtemp(join(tmpdir(), 'ginseng-panel-test-'));
after(() => rm(temporary, { recursive: true, force: true }));
await symlink(join(root, 'node_modules'), join(temporary, 'node_modules'), 'dir');
const format = ts.transpileModule(await readFile(join(root, 'src/lib/format.ts'), 'utf8'), {
	compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 }
}).outputText;
await writeFile(join(temporary, 'format.mjs'), format);
const source = await readFile(join(root, 'src/lib/components/OptimalPlanPanel.svelte'), 'utf8');
const compiled = compile(source.replace('$lib/format', './format.mjs'), { generate: 'server' });
await writeFile(join(temporary, 'panel.mjs'), compiled.js.code);
const { default: Panel } = await import(pathToFileURL(join(temporary, 'panel.mjs')).href);

function response(overrides = {}) {
	return {
		operating_buffer: 1000,
		optimizer_status: { code: 'optimal', message: 'Ready', paths: 2000, time_limit_seconds: 10 },
		optimal_plan: {
			credit_draw: 200, liquidation_amount: 1234, deferral_fraction: 0.1,
			expected_cost: 12, cvar_cost: 45, cost_coverage_target: 0.95,
			cash_shortfall_probability: 0.11, buffer_breach_probability: 0.3,
			evaluation_paths: 2000, evaluation_horizon_days: 38,
			dollar_days_below_buffer: 1500, buffer_tolerance_dollar_days: 1900,
			buffer_constraint_binding: false, implied_liquidity_price: 0.000000001,
			cost_is_path_dependent: true
		},
		...overrides
	};
}

function text(props) {
	return render(Panel, { props: { onRetry() {}, onLoadExample() {}, ...props } })
		.body.replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim();
}

test('shows funding amounts, average and tail costs, and the actual risk contract', () => {
	const output = text({ response: response() });
	for (const value of ['$200', '$1,234', '10%', '$12', '$45', '11%', '30%', '38-day']) {
		assert.ok(output.includes(value), value);
	}
	assert.match(output, /worst 5%/);
	assert.match(output, /does not require 95%/);
	assert.match(output, /1,500 dollar-days/);
	assert.match(output, /1,900 dollar-days/);
	assert.match(output, /not binding/);
	assert.doesNotMatch(output, /1e-9|NaN/);
});

test('loading hides the previous solution', () => {
	const output = text({ loading: true, response: response() });
	assert.match(output, /Finding a funding mix/);
	assert.doesNotMatch(output, /\$1,234|\$45|11%/);
});

test('shows gross withdrawal separately from its tax reserve, penalty, and spendable cash', () => {
	const data = response();
	data.optimal_plan.liquidation_amount = 1000;
	data.optimal_plan.withdrawal_net_cash = 660;
	data.optimal_plan.withdrawal_accounts = [
		{ account_type: 'traditional', gross: 1000, tax_reserve: 240, penalty_reserve: 100, net_cash: 660 },
		{ account_type: 'roth', gross: 0, tax_reserve: 0, penalty_reserve: 0, net_cash: 0 }
	];
	const output = text({ response: data });
	for (const value of ['Traditional IRA', 'Roth IRA contributions', '$1,000', '$240', '$100', '$660', 'Penalty reserve']) {
		assert.ok(output.includes(value), value);
	}
	assert.match(output, /Only the spendable amount enters the cash forecast/);
});

test('covered reserve offers a repair example instead of an empty optimizer', () => {
	const output = text({ response: response({
		optimal_plan: null,
		optimizer_status: { code: 'not_needed', message: 'Current cash covers the reserve.' }
	}) });
	assert.match(output, /No additional funding needed/);
	assert.match(output, /Load repair example/);
});

for (const [code, message] of [
	['solver_timeout', 'Optimization timed out after 10 seconds at 3,000 paths.'],
	['infeasible', 'No funding mix meets the average buffer deficit limit.'],
	['cvxpy_unavailable', 'The optimization library is unavailable.']
]) {
	test(`shows a readable ${code} failure with a retry action`, () => {
		const output = text({ response: response({
			optimal_plan: null, optimizer_status: { code, message }
		}) });
		assert.ok(output.includes(message));
		assert.match(output, /Retry analysis/);
		assert.match(output, /Named funding plans remain available/);
		assert.doesNotMatch(output, /\$1,234|Average cost/);
	});
}

test('100% tail setting describes the worst future rather than a zero-size tail', () => {
	const data = response();
	data.optimal_plan.cost_coverage_target = 1;
	const output = text({ response: data });
	assert.match(output, /Worst future cost/);
	assert.doesNotMatch(output, /worst 0%/);
});

test('an older response produces an explicit unavailable state', () => {
	const output = text({ response: response({ optimizer_status: undefined }) });
	assert.match(output, /Optimized mix unavailable/);
	assert.doesNotMatch(output, /NaN|undefined|\$1,234/);
});
