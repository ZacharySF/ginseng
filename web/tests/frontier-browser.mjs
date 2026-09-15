// Render the real Svelte/Plotly components with frozen synthetic engine output.
import assert from 'node:assert/strict';
import { checkKeyboardOrbit } from './helpers/graph-camera.mjs';
import { checkGraphFullscreen } from './helpers/graph-fullscreen.mjs';
import { mkdtemp, readFile, writeFile, symlink, rm, mkdir } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createServer } from 'vite';
import { svelte } from '@sveltejs/vite-plugin-svelte';
import { chromium } from 'playwright';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const temp = await mkdtemp(join(tmpdir(), 'ginseng-frontier-browser-'));
const fixture = JSON.parse(await readFile(join(root, 'tests/fixtures/portfolio-frontier.json'), 'utf8'));
await symlink(join(root, 'node_modules'), join(temp, 'node_modules'), 'dir');
await writeFile(join(temp, 'package.json'), '{"type":"module"}');
await writeFile(join(temp, 'index.html'), '<!doctype html><html><head><meta name="viewport" content="width=device-width, initial-scale=1"/></head><body><div id="app"></div><script type="module" src="/main.ts"></script></body></html>');
await writeFile(join(temp, 'paths.ts'), 'export const resolve = path => path;');
await writeFile(join(temp, 'transport.ts'), `
async function post(path, request, signal) {
 try {
  const response = await fetch('/mock/' + path, { method: 'POST', body: JSON.stringify(request), signal });
  return response.ok ? { status: 'ok', data: await response.json() } : { status: 'engine-error', message: 'The engine is busy. Try again.' };
 } catch { return { status: 'engine-error', message: 'Cancelled' }; }
}
export const postScenario = request => post('scenario', request);
export const postAnalysis = (kind, request, signal) => post(kind, request, signal);
`);
await writeFile(join(temp, 'main.ts'), `
import { mount } from 'svelte';
import Panel from '${root}/src/lib/components/PortfolioFrontier.svelte';
import Research from '${root}/src/routes/(app)/demo/research/+page.svelte';
import '${root}/src/app.css';
import '@fontsource-variable/archivo-narrow';
if (new URL(location.href).searchParams.has('route')) mount(Research, { target: document.getElementById('app') });
else mount(Panel, { target: document.getElementById('app'), props: { report: ${JSON.stringify(fixture)} } });
`);
const server = await createServer({
 configFile: false, root: temp, plugins: [svelte({ configFile: false })],
 resolve: { alias: { '$lib': join(root, 'src/lib'), '$app/paths': join(temp, 'paths.ts'), './api': join(temp, 'transport.ts') }, dedupe: ['svelte'] },
 server: { port: 0, host: '127.0.0.1', fs: { allow: [root, temp] } }
});
let browser;
try {
 await server.listen();
 browser = await chromium.launch({ headless: true,
  ...(process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {}),
  args: ['--no-sandbox', '--enable-unsafe-swiftshader']
 });
 const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } });
 const shots = process.env.FRONTIER_SCREENSHOTS;
 if (shots) await mkdir(shots, { recursive: true });
 const errors = [];
 page.on('pageerror', error => errors.push(error.message));
 await page.goto(`http://127.0.0.1:${server.httpServer.address().port}`);
 await page.waitForFunction(() => document.querySelector('.frontier-plot')?._fullLayout?.scene?._scene?.glplot);
 const plot = page.locator('.frontier-plot');
 const selector = page.getByLabel('Select a portfolio', { exact: true });
 await page.waitForFunction(() => {
  const el = document.querySelector('.frontier-plot');
  return el?._fullLayout?.width <= el.clientWidth + 1 && el._fullLayout.scene.dragmode === 'orbit';
 });
 await page.waitForTimeout(350); // Let the initial WebGL camera relayout finish.
 assert.equal(await selector.inputValue(), 'current');
 assert.equal(await plot.evaluate(el => el.layout.paper_bgcolor), '#f7f7f2', 'light plotting field matches the application paper theme');
 assert.equal(await page.locator('.orientation-gizmo').count(), 1, 'view includes a camera orientation triad');
 assert.deepEqual(await plot.evaluate(el => {
  const projection = el.data.find(row => row.name === 'Floor projection');
  return { x: projection.x, y: projection.y };
 }), { x: fixture.points.map(point => point.discovery.volatility), y: fixture.points.map(point => point.discovery.mean_return) }, 'floor projection uses actual allocation coordinates');
 const current = fixture.points.find(point => point.id === 'current');
 assert.deepEqual(await plot.evaluate(el => {
  const trace = el.data.find(row => row.name === 'Current allocation');
  return [trace.x[0], trace.y[0], trace.z[0]];
 }), [current.discovery.volatility, current.discovery.mean_return, current.discovery.pressure_cvar]);

 const original = await plot.evaluate(el => el.layout.scene.camera);
 const originalAxes = await page.locator('.orientation-gizmo').innerHTML();
 const box = await plot.boundingBox();
 await page.mouse.move(box.x + box.width * .5, box.y + box.height * .5);
 await page.mouse.down();
 await page.mouse.move(box.x + box.width * .65, box.y + box.height * .6, { steps: 12 });
 await page.mouse.up();
 assert.equal(await plot.evaluate(el => document.activeElement === el), true, 'pointer interaction focuses the chart for keyboard controls');
 assert.notDeepEqual(await plot.evaluate(el => el.layout.scene.camera), original, 'pointer drag rotates actual 3D camera');
 assert.equal(await selector.inputValue(), 'current', 'dragging across a point does not select it');
 await page.waitForFunction(previous => document.querySelector('.orientation-gizmo')?.innerHTML !== previous, originalAxes);
 await page.getByRole('button', { name: 'Reset camera' }).click();
 await page.waitForFunction(() => document.querySelector('.frontier-plot')?.layout?.scene?.camera?.eye?.x === 1.3);
 await checkKeyboardOrbit(page, '.frontier-plot', {
  reset: 'Reset camera', flat: 'Risk / return', perspective: '3D', control: '#allocation-select',
  metrics: () => plot.evaluate(el => el.data.filter(trace => trace.customdata).map(trace => ({
   id: trace.customdata, x: trace.x, y: trace.y, z: trace.z
  })))
 });
 assert.equal(await page.getByRole('button', { name: 'Discovery sample', exact: true }).getAttribute('aria-pressed'), 'true', 'keyboard camera controls preserve the selected sample');
 // Fullscreen must preserve a nondefault allocation and the fresh sample.
 await selector.selectOption('equal-weight');
 await page.getByRole('button', { name: 'Fresh-sample check', exact: true }).click();
 await page.waitForFunction(() => document.querySelector('.frontier-plot')?.data.some(trace => trace.name === 'Selected: discovery → check'));
 await checkGraphFullscreen(page, '.frontier-plot', {
  reset: 'Reset camera', control: '#allocation-select',
  screenshot: shots ? join(shots, 'frontier-fullscreen.png') : undefined,
  metrics: () => plot.evaluate(el => el.data.filter(trace => trace.customdata).map(trace => ({
   id: trace.customdata, x: trace.x, y: trace.y, z: trace.z
  })))
 });
 assert.equal(await selector.inputValue(), 'equal-weight');
 assert.equal(await page.getByRole('button', { name: 'Fresh-sample check', exact: true }).getAttribute('aria-pressed'), 'true', 'fullscreen preserves the selected evaluation sample');
 await selector.selectOption('current');
 await page.getByRole('button', { name: 'Discovery sample', exact: true }).click();
 await page.waitForFunction(() => !document.querySelector('.frontier-plot')?.data.some(trace => trace.name === 'Selected: discovery → check'));
 await page.getByRole('button', { name: 'Risk / return', exact: true }).click();
 await page.waitForFunction(() => document.querySelector('.frontier-plot')?.layout?.scene?.camera?.projection?.type === 'orthographic');
 assert.equal(await plot.evaluate(el => el.layout.scene.zaxis.showticklabels), false, 'risk/return projection hides only tail axis');
 assert.equal(await selector.inputValue(), 'current', 'camera presets preserve selected portfolio');
 if (shots) { await page.waitForTimeout(350); await page.screenshot({ path: join(shots, 'frontier-risk-return.png'), fullPage: true }); }
 await page.getByRole('button', { name: 'Tail / return', exact: true }).click();
 await page.waitForFunction(() => document.querySelector('.frontier-plot')?.layout?.scene?.xaxis?.showticklabels === false);
 assert.equal(await plot.evaluate(el => el.layout.scene.zaxis.showticklabels), true);
 if (shots) { await page.waitForTimeout(350); await page.screenshot({ path: join(shots, 'frontier-tail-return.png'), fullPage: true }); }
 await page.getByRole('button', { name: '3D', exact: true }).click();
 await page.waitForFunction(() => document.querySelector('.frontier-plot')?.layout?.scene?.camera?.projection?.type === 'perspective');

 // Exercise keyboard selection and the Plotly click event's application wiring.
 const cameraBeforeSelector = await plot.evaluate(el => el.layout.scene.camera);
 await selector.focus();
 await page.keyboard.press('ArrowDown');
 await page.keyboard.press('Enter');
 assert.equal(await selector.inputValue(), 'equal-weight');
 assert.deepEqual(await plot.evaluate(el => el.layout.scene.camera), cameraBeforeSelector, 'native selector arrows do not orbit the camera');
 await plot.evaluate(el => el.emit('plotly_click', { points: [{ customdata: 'pure-2' }] }));
 await page.waitForFunction(() => document.querySelector('#allocation-select').value === 'pure-2');
 assert.equal(await page.locator('.weight-row').last().innerText(), 'CASH\n100.00%');
 assert.equal(await page.locator('.metrics tbody tr').first().innerText(), 'Expected return ↑\t0.00%\t0.00%');

 await selector.selectOption('current');
 await page.getByRole('button', { name: 'Fresh-sample check', exact: true }).click();
 await page.waitForFunction(() => document.querySelector('.frontier-plot')?.data.some(row => row.name === 'Selected: discovery → check'));
 assert.equal(await selector.inputValue(), 'current', 'holdout preserves allocation selection');
 assert.equal(await plot.evaluate(el => el.data.find(row => row.name === 'Current allocation').z[0]), current.evaluation.pressure_cvar);
 assert.equal(await plot.evaluate(el => el.data.find(row => row.name === 'Discovery Pareto set').x.length), fixture.points.filter(point => point.pareto).length, 'holdout preserves discovery membership');
 await page.getByLabel('Focus on Pareto candidates').check();
 await page.waitForFunction(() => !document.querySelector('.frontier-plot')?.data.some(row => row.name === 'Other explored allocations'));

 const downloadEvent = page.waitForEvent('download');
 await page.getByRole('button', { name: 'Export JSON' }).click();
 const download = await downloadEvent;
 assert.deepEqual(JSON.parse(await readFile(await download.path(), 'utf8')), fixture, 'export retains exact engine results');
 await page.getByRole('button', { name: 'Show all allocation values' }).click();
 assert.equal(await page.locator('.allocation-table tbody tr').count(), fixture.points.length);
 await page.getByRole('button', { name: 'Hide all allocation values' }).click();
 await page.getByLabel('Focus on Pareto candidates').uncheck();
 await page.getByRole('button', { name: 'Discovery sample', exact: true }).click();
 await page.waitForTimeout(500);
 if (shots) {
  await page.screenshot({ path: join(shots, 'frontier-light.png'), fullPage: true });
  await page.locator('.chart-frame').screenshot({ path: join(shots, 'frontier-field.png') });
 }

 await page.evaluate(async root => { const module = await import('/@fs' + root + '/src/lib/theme.svelte.ts'); module.themeStore.toggle(); }, root);
 await page.waitForFunction(() => document.querySelector('.frontier-plot')?.layout?.paper_bgcolor === '#050e1a');
 if (shots) await page.screenshot({ path: join(shots, 'frontier-dark.png'), fullPage: true });
 await page.getByRole('button', { name: 'Fresh-sample check', exact: true }).click();
 await page.waitForTimeout(500);
 if (shots) await page.screenshot({ path: join(shots, 'frontier-check.png'), fullPage: true });
 await page.setViewportSize({ width: 390, height: 844 });
 await page.waitForFunction(() => {
  const el = document.querySelector('.frontier-plot');
  return el?._fullLayout?.width <= el.clientWidth + 1 && el.layout.scene.camera.eye.x === 1.45;
 });
 await page.waitForTimeout(700);
 assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1), 'no mobile horizontal overflow');
 assert.ok(Math.abs(await plot.evaluate(el => el._fullLayout.scene._scene.getCamera().eye.x) - 1.45) < 1e-6);
 if (shots) await page.screenshot({ path: join(shots, 'frontier-mobile.png'), fullPage: true });

 // The actual route and request stores, with only HTTP transport mocked.
 let fail = false;
 let lastRequest;
 await page.route('**/mock/scenario', route => route.fulfill({ contentType: 'application/json', body: '{"baseline_summary":{}}' }));
 await page.route('**/mock/frontier', route => {
  lastRequest = route.request().postDataJSON();
  return route.fulfill({ status: fail ? 503 : 200, contentType: 'application/json', body: JSON.stringify(
   lastRequest.obligations.length ? fixture : { status: 'unavailable', message: 'Too few cash-pressure paths for a conditional estimate.' }
  ) });
 });
 await page.setViewportSize({ width: 1440, height: 1100 });
 await page.goto(`http://127.0.0.1:${server.httpServer.address().port}/?route`);
 const build = page.getByRole('button', { name: 'Build portfolio frontier', exact: true });
 await build.click();
 await page.getByRole('heading', { name: 'This experiment is unavailable' }).waitFor();
 assert.equal(await page.locator('.frontier-plot').count(), 0);
 await page.getByRole('button', { name: 'Load repair case', exact: true }).click();
 await build.click();
 await page.waitForFunction(() => document.querySelector('.frontier-plot')?._fullLayout?.scene?._scene?.glplot);
 assert.deepEqual(lastRequest.obligations.map(row => [row.amount, row.due_in_days]), [[1500, 3], [3000, 17]]);
 assert.equal(lastRequest.horizon_days, 30);
 if (shots) {
  await page.waitForTimeout(500);
  await page.screenshot({ path: join(shots, 'research-page.png'), fullPage: true });
 }
 await page.evaluate(async root => {
  const { scenarioStore } = await import('/@fs' + root + '/src/lib/scenario.svelte.ts');
  scenarioStore.setHorizonDays(60);
 }, root);
 await page.waitForFunction(() => document.querySelector('.frontier-plot') === null);
 fail = true;
 await build.click();
 await page.getByRole('alert').filter({ hasText: 'The engine is busy' }).waitFor();
 assert.equal(lastRequest.horizon_days, 60);
 assert.equal(await page.locator('.frontier-plot').count(), 0, 'failed analysis cannot retain an old scenario plot');
 await page.evaluate(async root => {
  const { scenarioStore } = await import('/@fs' + root + '/src/lib/scenario.svelte.ts');
  scenarioStore.setStressProbability(0.5);
 }, root);
 await page.getByText('Disable stress weighting and choose a horizon of 60 days or less to use this research model.', { exact: true }).waitFor();
 assert.equal(await build.isDisabled(), true);
 assert.deepEqual(errors, []);
 console.log('Browser passed: 3D rendering, pointer/keyboard camera controls, native/fallback fullscreen, focus/native-control isolation, selection, holdout, Pareto filter, export/table, themes/mobile, repair route, stale-result clearing, unsupported mode and errors.');
} finally {
 if (browser) await browser.close();
 await server.close();
 await rm(temp, { recursive: true, force: true });
}
