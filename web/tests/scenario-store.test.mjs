import assert from 'node:assert/strict';
import { after, test } from 'node:test';
import { mkdtemp, readFile, rm, symlink, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { compileModule } from 'svelte/compiler';
import ts from 'typescript';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const temporary = await mkdtemp(join(tmpdir(), 'ginseng-store-test-'));
after(() => rm(temporary, { recursive: true, force: true }));
await symlink(join(root, 'node_modules'), join(temporary, 'node_modules'), 'dir');
await writeFile(join(temporary, 'api.mjs'), `
export const calls = [];
export function postScenario(request) {
  return new Promise(resolve => calls.push({ request: structuredClone(request), resolve }));
}`);
const source = ts.transpileModule(await readFile(join(root, 'src/lib/scenario.svelte.ts'), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 }
}).outputText.replace("'./api'", "'./api.mjs'");
await writeFile(join(temporary, 'store.mjs'), compileModule(source, { generate: 'client' }).js.code);
const { ScenarioStore } = await import(pathToFileURL(join(temporary, 'store.mjs')).href);
const { calls } = await import(pathToFileURL(join(temporary, 'api.mjs')).href);
const tick = () => new Promise(resolve => setTimeout(resolve, 0));
function complete(call, marker = 1) {
  call.resolve({ status: 'ok', data: { funding_gap: marker, baseline_summary: { funding_gap: 0 } } });
}

test('keeps event dates when the chart is shortened and does not duplicate baseline requests', async () => {
  const store = new ScenarioStore();
  const start = calls.length;
  store.loadRepairExample();
  assert.equal(calls.length, start + 1);
  complete(calls.at(-1)); await tick();
  store.setHorizonDays(14);
  assert.deepEqual(store.request.obligations.map(o => o.due_in_days), [3, 17]);
  assert.deepEqual(calls.at(-1).request.obligations.map(o => o.due_in_days), [3, 17]);
  complete(calls.at(-1)); await tick();
  assert.equal(calls.length, start + 2);
});

test('coalesces rapid edits and never displays a superseded response', async () => {
  const store = new ScenarioStore();
  const start = calls.length;
  store.ensureLoaded();
  store.setOperatingBuffer(500);
  store.setOperatingBuffer(600);
  store.setOperatingBuffer(700);
  assert.equal(calls.length, start + 1);
  assert.equal(store.response, null);
  complete(calls[start], 123); await tick();
  assert.equal(store.response, null);
  assert.equal(calls.length, start + 2);
  assert.equal(calls[start + 1].request.operating_buffer, 700);
  complete(calls[start + 1], 456); await tick();
  assert.equal(store.response.funding_gap, 456);
  assert.equal(store.baselineResponse.funding_gap, 0);
});

test('rejects invalid policy values and adds missing repair events only once', async () => {
  const store = new ScenarioStore();
  const start = calls.length;
  store.setOperatingBuffer(Infinity); store.setCoverageTarget(2); store.setHorizonDays(366);
  assert.equal(calls.length, start);
  store.loadRepairExample(); complete(calls.at(-1)); await tick();
  store.removeObligation('repair-balance'); complete(calls.at(-1)); await tick();
  store.applyShock();
  assert.deepEqual(store.request.obligations.map(o => o.id).sort(), ['repair-balance', 'repair-deposit']);
  complete(calls.at(-1)); await tick();
});

test('sets both risk limits in one request and preserves zero as a real constraint', async () => {
  const store = new ScenarioStore();
  const start = calls.length;
  store.setRiskLimits(0, 250);
  assert.equal(calls.length, start + 1);
  assert.equal(calls.at(-1).request.tail_deficit_limit, 0);
  assert.equal(calls.at(-1).request.buffer_tolerance_dollar_days, 250);
  complete(calls.at(-1)); await tick();
});
