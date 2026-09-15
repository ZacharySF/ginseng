<script lang="ts">
	import '$lib/analysis.css';
	import { scenarioStore } from '$lib/scenario.svelte';
	import { AnalysisStore } from '$lib/analysis.svelte';
	import type { CalibrationReport } from '$lib/analysis-types';
	import type { ScenarioResponse } from '$lib/types';
	import { formatCurrency, formatPercent } from '$lib/format';
	let { response, report: externalReport = null, loading = false, error = null, onRun, allowHistorical = true }: {
        response: ScenarioResponse; report?: CalibrationReport | null; loading?: boolean;
        error?: string | null; onRun?: () => void | Promise<void>; allowHistorical?: boolean;
    } = $props();
	const analysis = new AnalysisStore<CalibrationReport>('calibration');
	const revision = $derived(JSON.stringify(scenarioStore.request));
	$effect(() => { revision; analysis.reset(); });
	const card = $derived(response.model_card);
	const report = $derived(onRun ? externalReport : analysis.data);
    const busy = $derived(onRun ? loading : analysis.loading);
    const failure = $derived(onRun ? error : analysis.error);
    const rows = $derived(report?.windows ?? []);
	const high = $derived(Math.max(1, ...rows.flatMap(r => [r.predicted_reserve, r.realized_required])));
	const x = (i: number) => 55 + i * 535 / Math.max(1, rows.length - 1);
	const y = (value: number) => 205 - value / high * 165;
</script>

<section class="analysis-panel" id="model-evidence" aria-label="Model evidence">
	<h2>What the model knows</h2>
	<p><strong>{card?.evidence_statement ?? 'More simulations improve numerical precision. They do not create more historical evidence.'}</strong></p>
	{#if card?.version}
		<p>{card.history_days} days of history · {card.simulation_paths.toLocaleString()} simulated futures. {card.source}</p>
		<details><summary>Model card · version {card.version}</summary>
			<p>{card.purpose}</p><p><strong>Predicted quantity:</strong> {card.target}</p>
			<p>{card.history_days ? `History: ${card.history_start} through ${card.history_end}.` : "No historical sample is used by this forecast."}</p>
			<h3>Assumptions and limitations</h3><ul>{#each card.limitations as limitation}<li>{limitation}</li>{/each}</ul>
			<h3>When recommendations stop</h3><ul>{#each card.recommendation_gates as gate}<li>{gate}</li>{/each}</ul>
			<h3>Outside this model's purpose</h3><ul>{#each card.prohibited_uses as use}<li>{use}</li>{/each}</ul>
			<p><a href={card.guidance.url} target="_blank" rel="noreferrer">{card.guidance.name}</a>. {card.guidance.use}</p>
		</details>
	{/if}
	<details><summary>Reproduce this run</summary>
		<p>Paths, probability weights, stress assumptions, model configuration, and inputs have separate fingerprints. A weight change is a different run even when its futures are unchanged.</p>
		{#each Object.entries(response.provenance ?? {}) as [name, hash]}<strong>{name.replaceAll('_', ' ')}</strong><code class="fingerprint">{hash}</code>{/each}
	</details>
	{#if allowHistorical}
	<h3>Test against later history</h3>
	<p>Train on the past, predict the next window, then compare with what happened. Today's added events and stress assumptions are excluded from this historical check.</p>
	<button class="primary" type="button" disabled={busy} onclick={() => onRun ? onRun() : analysis.run(scenarioStore.request)}>{busy ? 'Checking historical windows…' : report ? 'Run historical check again' : 'Run historical check'}</button>
	{#if failure}<p class="analysis-alert" role="alert">{failure}</p>{/if}
	{#if report}
		{@const sample = report.primary}
		<div class="analysis-grid">
			<div><small>Nominal coverage</small><strong class="analysis-value">{formatPercent(report.nominal_coverage)}</strong></div>
			<div><small>Non-overlapping windows held</small><strong class="analysis-value">{sample.covered} of {sample.windows}</strong></div>
			<div><small>95% reference interval</small><strong class="analysis-value">{sample.interval ? `${formatPercent(sample.interval.low)}–${formatPercent(sample.interval.high)}` : 'Unavailable'}</strong></div>
		</div>
		<p class="analysis-note">{report.training_days_minimum} initial days train the first forecast. {report.interval_note}</p>
		<p>{report.source}</p>
		{#if report.status === 'insufficient_history'}<p class="analysis-alert">There is not enough history after the initial training period for a complete forecast window.</p>{/if}
		<div class="analysis-table"><table><caption>Results at different window spacings</caption><thead><tr><th>Spacing</th><th>Windows held</th><th>Pinball loss</th><th>CRPS</th></tr></thead><tbody>
			{#each report.spacing_results as row}<tr><td>{row.spacing_days} days · {row.overlapping ? 'overlapping' : 'non-overlapping'}</td><td>{row.covered} / {row.windows}</td><td>{row.mean_pinball_loss === null ? 'Unavailable' : formatCurrency(row.mean_pinball_loss)}</td><td>{row.mean_crps === null ? 'Unavailable' : formatCurrency(row.mean_crps)}</td></tr>{/each}
		</tbody></table></div>
		<p class="analysis-note">Lower scoring losses are better. Pinball loss checks the selected reserve quantile; CRPS checks the whole predicted distribution.</p>
		{#if rows.length}
			<h3>Predicted reserve and realized cash requirement</h3>
			<svg class="analysis-plot" viewBox="0 0 640 245" role="img" aria-label="Historical reserve predictions and realized cash requirements">
				<line x1="55" x2="590" y1="205" y2="205" stroke="var(--rule)" />
				<polyline points={rows.map((r,i) => `${x(i)},${y(r.predicted_reserve)}`).join(' ')} fill="none" stroke="var(--cobalt)" stroke-width="2" />
				<polyline points={rows.map((r,i) => `${x(i)},${y(r.realized_required)}`).join(' ')} fill="none" stroke="var(--negative)" stroke-width="2" />
				{#each rows as row,i}<circle cx={x(i)} cy={y(row.realized_required)} r={row.in_primary_sample ? 3 : 1.5} fill="var(--negative)"><title>{row.start}–{row.end}: predicted {formatCurrency(row.predicted_reserve)}, realized {formatCurrency(row.realized_required)}. Trained through {row.training_cutoff}.</title></circle>{/each}
				<text x="55" y="22">{formatCurrency(high)}</text><text x="55" y="229">{rows[0].start}</text><text x="590" y="229" text-anchor="end">{rows[rows.length-1].start}</text>
			</svg>
			<p class="analysis-note">Blue: predicted reserve. Red: realized requirement. {report.descriptive_windows} overlapping and non-overlapping windows enrich this chart; only {sample.windows} non-overlapping windows enter the main count.</p>
			<h3>Where reality landed in the predictions</h3>
			<svg class="analysis-plot" viewBox="0 0 640 160" role="img" aria-label="Randomized PIT histogram of non-overlapping historical windows">
				{#each report.pit.counts as count,i}<rect x={55+i*53} y={120-count/Math.max(1,...report.pit.counts)*90} width="46" height={count/Math.max(1,...report.pit.counts)*90} fill="var(--cobalt)"><title>{i*10}–{(i+1)*10}th percentile: {count} windows</title></rect>{/each}
				<text x="55" y="145">0th percentile</text><text x="585" y="145" text-anchor="end">100th percentile</text>
			</svg><p class="analysis-note">{report.pit.method} Tied predictions, including zero, are spread within their percentile interval so ties do not create false spikes.</p>
		{/if}
		<details><summary>Target definition and formal tests</summary><p>{report.target}</p><p>{report.excluded}</p>
			<p>Expected tail failures: {report.expected_tail_failures.toFixed(1)}. Five expected failures is only a minimum screening rule, not proof of adequate power.</p>
			{#each Object.entries(report.formal_tests) as [name, test]}<p><strong>{name.replaceAll('_',' ')}:</strong> {test.status === 'computed' ? `p-value ${test.p_value?.toFixed(3)}. ${test.caveat}` : test.reason}</p>{/each}
		</details>
	{/if}
{/if}
</section>
