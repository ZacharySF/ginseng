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
const temporary = await mkdtemp(join(tmpdir(), 'ginseng-analysis-test-'));
after(() => rm(temporary, { recursive: true, force: true }));
await symlink(join(root, 'node_modules'), join(temporary, 'node_modules'), 'dir');
await writeFile(join(temporary, 'state.mjs'), `
export const scenarioStore = { request: {} };
let result = null;
export const setResult = value => result = value;
export class AnalysisStore { data = result; loading = false; error = ''; }
`);
const format = ts.transpileModule(await readFile(join(root, 'src/lib/format.ts'), 'utf8'), {
	compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 }
}).outputText;
await writeFile(join(temporary, 'format.mjs'), format);
const source = (await readFile(join(root, 'src/lib/components/FundingAnalysisPanel.svelte'), 'utf8'))
	.replace("import '$lib/analysis.css';", '')
	.replace('$lib/scenario.svelte', './state.mjs')
	.replace('$lib/analysis.svelte', './state.mjs')
	.replace('$lib/format', './format.mjs');
await writeFile(join(temporary, 'panel.mjs'), compile(source, { generate: 'server' }).js.code);
const { default: Panel } = await import(pathToFileURL(join(temporary, 'panel.mjs')).href);
const { setResult } = await import(pathToFileURL(join(temporary, 'state.mjs')).href);

test('unsupported stress displays its reason without requiring missing chart fields', () => {
	setResult({ status: 'unavailable', reason: 'The requested stress has no supporting scenarios.' });
	const output = render(Panel).body;
	assert.match(output, /The requested stress has no supporting scenarios/);
	assert.doesNotMatch(output, /NaN|undefined|shared futures/);
});

test('infeasible solves retain the completed named-plan comparison', () => {
	setResult({ status: 'unavailable', reason: 'infeasible', paths: 100, evaluation_horizon_days: 38,
		frontier: [], shadow_checks: [], holdout: null,
		anchors: [{ label: 'Credit Bridge', feasible: false, expected_cost: 10, cvar_cost: 20, tail_deficit: 500 }],
		loss_definition: 'Shared loss definition', risk_definition: 'Shared risk definition' });
	const output = render(Panel).body;
	assert.match(output, /infeasible/);
	assert.match(output, /Credit Bridge/);
	assert.match(output, /Funding operation unavailable/);
});

test('frozen holdout shows numerical policy failures and a named fixed-sample interval', () => {
    setResult({ status: 'ready', paths: 100, evaluation_horizon_days: 38,
        frontier: [], shadow_checks: [], anchors: [],
        holdout: { status: 'ready', label: 'Frozen selected plan', expected_cost: 3, cvar_cost: 5,
            cash_shortfall_probability: .2, within_mean_buffer_limit: false, within_tail_deficit_limit: null,
            verification: { status: 'failed', metrics: { cash_failure_probability: .2 } },
            interval: { low: .1, high: .3, method: 'Clopper-Pearson fixed-sample exact binomial' } },
        loss_definition: '', risk_definition: '' });
    const output = render(Panel).body;
    assert.match(output, /training constraint was exceeded/);
    assert.match(output, /Clopper-Pearson/);
    assert.match(output, /Simulator validation is separate from historical calibration/);
});
