<script lang="ts">
	import type { FrontierReady } from '$lib/frontier-types';
	import '$lib/chart-lab.css';
	import FrontierChart from './FrontierChart.svelte';
	let { report }: { report: FrontierReady } = $props();
	let selectedId = $state('');
	let view = $state<'discovery' | 'evaluation'>('discovery');
	let frontierOnly = $state(false);
	let showTable = $state(false);
	const selected = $derived(report.points.find(point => point.id === selectedId) ?? report.points.find(point => point.id === 'current') ?? report.points[0]);
	const frontier = $derived(report.points.filter(point => point.pareto));
	const pct = (value: number) => `${(100 * value).toFixed(2)}%`;
	function download() {
		const url = URL.createObjectURL(new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' }));
		const anchor = document.createElement('a'); anchor.href = url; anchor.download = 'ginseng-portfolio-frontier.json';
		anchor.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
	}
</script>

<section class="frontier-results lab-view" aria-label="Portfolio frontier research results">
	<div class="experiment-strip">
		<div><span class="lab-kicker">Allocation space</span><strong>{report.points.length} <small>portfolios</small></strong></div>
		<div><span class="lab-kicker">Pareto set</span><strong>{frontier.length} <small>candidates</small></strong></div>
		<div><span class="lab-kicker">Forecast window</span><strong>{String(report.metadata.horizon_days)} <small>days</small></strong></div>
		<button class="lab-button" onclick={download}>Export JSON <span aria-hidden="true">↗</span></button>
	</div>
	<div class="lab-toolbar sample-toolbar">
		<div class="lab-switch" aria-label="Evaluation sample">
			<button aria-label="Discovery sample" aria-pressed={view === 'discovery'} onclick={() => view = 'discovery'}><span class="step" aria-hidden="true">01</span> Discovery sample</button>
			<button aria-label="Fresh-sample check" aria-pressed={view === 'evaluation'} onclick={() => view = 'evaluation'}><span class="step" aria-hidden="true">02</span> Fresh-sample check</button>
		</div>
		<label class="filter"><input type="checkbox" bind:checked={frontierOnly}/> Focus on Pareto candidates</label>
	</div>
	<p class="view-note">{view === 'discovery' ? 'Each point is one portfolio. Blue points mark tradeoffs where no explored alternative improves one objective without worsening another.' : 'Same portfolios, new simulated futures. Blue labels stay fixed; the selected line shows how its estimates move between samples.'}</p>
	<div class="workbench">
		<FrontierChart {report} selectedId={selected.id} {view} {frontierOnly} onSelect={id => selectedId = id}/>
		<aside aria-label="Selected allocation details">
			<div class="inspector-heading"><p class="lab-kicker">Portfolio inspector</p><span class="selection-ring" aria-hidden="true"></span></div>
			<label for="allocation-select">Select a portfolio</label>
			<select id="allocation-select" value={selected.id} onchange={event => selectedId = event.currentTarget.value}>
				{#each report.points as point}<option value={point.id}>{point.label}{point.pareto ? ' · Pareto' : ''}</option>{/each}
			</select>
			<p class="point-status" class:efficient={selected.pareto}><span aria-hidden="true">{selected.pareto ? '●' : '○'}</span>{selected.pareto ? 'On the discovery Pareto frontier' : 'Outside the discovery Pareto frontier'}</p>
			<div class="inspector-section">
				<h3>Allocation weights</h3>
				{#each report.symbols as symbol, index}
					<div class="weight-row"><div><strong>{symbol}</strong><span>{pct(selected.weights[index])}</span></div><div class="weight-track"><span class:cash={symbol === 'CASH'} style:width={`${selected.weights[index] * 100}%`}></span></div></div>
				{/each}
				<p class="small">CASH earns zero here. It stays in the portfolio; bank cash and breach timing stay fixed.</p>
			</div>
			<div class="inspector-section">
				<h3>Model estimates <span>%</span></h3>
				<table class="metrics"><thead><tr><th>Objective</th><th class:active-column={view === 'discovery'}>Discovery</th><th class:active-column={view === 'evaluation'}>Check</th></tr></thead><tbody>
					<tr><th>Expected return ↑</th><td class:active-column={view === 'discovery'}>{pct(selected.discovery.mean_return)}</td><td class:active-column={view === 'evaluation'}>{pct(selected.evaluation.mean_return)}</td></tr>
					<tr><th>Volatility ↓</th><td class:active-column={view === 'discovery'}>{pct(selected.discovery.volatility)}</td><td class:active-column={view === 'evaluation'}>{pct(selected.evaluation.volatility)}</td></tr>
					<tr><th>Pressure tail loss ↓</th><td class:active-column={view === 'discovery'}>{pct(selected.discovery.pressure_cvar)}</td><td class:active-column={view === 'evaluation'}>{pct(selected.evaluation.pressure_cvar)}</td></tr>
				</tbody></table>
				<p class="small">Return and volatility cover this horizon. Tail loss averages the worst 5% of losses at the first cash-buffer breach, among paths that breach.</p>
			</div>
		</aside>
	</div>
	<div class="reading-strip"><span class="lab-kicker">Reading the view</span><p>Higher return, lower volatility and lower tail loss are preferred. The tradeoff between them is yours to inspect.</p></div>
	<details class="lab-disclosure">
		<summary>Understand the axes &amp; sample check</summary>
		<div class="method-notes">
			<div><h3>Why the third axis matters</h3><p>Volatility measures how widely horizon returns vary. The third axis measures portfolio loss when bank cash first falls below its operating buffer. Two portfolios can have similar ordinary risk yet different losses at that moment. Negative tail loss means a gain.</p></div>
			<div><h3>What the sample check tells you</h3><p>The second sample uses independent simulations from the same historical model. It probes numerical stability, not performance in a future historical period. Pareto membership is relative to the explored portfolios. Returns are not annualized.</p></div>
		</div>
	</details>
	<details class="lab-disclosure">
		<summary>Sampling &amp; optimization record</summary>
		<p class="small">{report.pressure.discovery_count} discovery paths and {report.pressure.evaluation_count} check paths breach the cash buffer. Their worst 5% contains {report.pressure.discovery_tail_mass_count.toFixed(1)} and {report.pressure.evaluation_tail_mass_count.toFixed(1)} scenario-equivalents, including fractional boundary observations. Small differences can be sensitive to a few scenarios.</p>
		<pre>{JSON.stringify(report.metadata, null, 2)}</pre>
	</details>
	<div class="table-toolbar"><button class="lab-button" aria-expanded={showTable} onclick={() => showTable = !showTable}>{showTable ? 'Hide' : 'Show'} all allocation values <span aria-hidden="true">{showTable ? '−' : '+'}</span></button><span class="lab-kicker">Exact values / {view === 'discovery' ? 'sample 01' : 'sample 02'}</span></div>
	{#if showTable}<div class="allocation-table"><table><caption>{view === 'discovery' ? 'Discovery sample' : 'Fresh-sample check'} · horizon returns and risks in percent</caption><thead><tr><th>Allocation</th><th>Return ↑</th><th>Volatility ↓</th><th>Pressure tail loss ↓</th><th>Discovery set</th></tr></thead><tbody>
		{#each report.points as point}<tr class:chosen={point.id === selected.id}><th><button onclick={() => selectedId = point.id}>{point.label}</button></th><td>{pct(point[view].mean_return)}</td><td>{pct(point[view].volatility)}</td><td>{pct(point[view].pressure_cvar)}</td><td>{point.pareto ? 'Pareto' : 'Other'}</td></tr>{/each}
	</tbody></table></div>{/if}
</section>
<style>
	.experiment-strip { display: flex; align-items: center; flex-wrap: wrap; gap: 2.5rem; padding: 1rem 1.2rem; border-bottom: 1px solid var(--rule); }
	.experiment-strip > div { display: grid; gap: .25rem; }.experiment-strip strong { font: 1.65rem var(--font-mono); letter-spacing: -.05em; }.experiment-strip small { font: .7rem var(--font-mono); color: var(--ink-soft); letter-spacing: 0; }.experiment-strip button { margin-left: auto; }
	.sample-toolbar { border-bottom: 0; }.step { opacity: .7; font-size: .6rem; }
	.filter { display: inline-flex; align-items: center; gap: .5rem; font: .7rem var(--font-mono); color: var(--ink-soft); cursor: pointer; }.filter input { width: 1rem; height: 1rem; accent-color: var(--cobalt); }
	.view-note { margin: 0; padding: 0 1rem .9rem; color: var(--ink-soft); font-size: .88rem; line-height: 1.45; border-bottom: 1px solid var(--rule); }
	.workbench { display: grid; grid-template-columns: minmax(0, 1fr) 20rem; }
	aside { min-width: 0; padding: 1.2rem; border-left: 1px solid var(--rule); background: var(--paper); }.inspector-heading { display: flex; justify-content: space-between; align-items: center; padding-bottom: 1.15rem; }.selection-ring { width: .65rem; height: .65rem; border: 1.5px solid var(--lab-selection); border-radius: 50%; }
	aside label { display: block; font-size: .85rem; color: var(--ink-soft); margin-bottom: .4rem; }select { width: 100%; min-height: 2.75rem; padding: .6rem; background: var(--paper-soft); color: var(--ink); border: 1px solid var(--control-border); border-radius: 0; font: .8rem var(--font-mono); cursor: pointer; }
	.point-status { display: flex; gap: .45rem; margin-top: .65rem; color: var(--ink-soft); font-size: .78rem; }.point-status.efficient { color: var(--cobalt); }
	.inspector-section { padding-top: 1.25rem; margin-top: 1.2rem; border-top: 1px solid var(--rule); }
	h3 { font-size: 1rem; font-weight: 600; margin-bottom: .85rem; }.inspector-section h3 { display: flex; justify-content: space-between; }.inspector-section h3 span { color: var(--ink-muted); font: .7rem var(--font-mono); }
	.weight-row { margin: .9rem 0; }.weight-row > div:first-child { display: flex; justify-content: space-between; font: .76rem var(--font-mono); margin-bottom: .45rem; }.weight-row strong { font-weight: 500; }.weight-track { height: .3rem; background: var(--paper-deep); }.weight-track span { display: block; height: 100%; background: var(--cobalt); }.weight-track span.cash { background: var(--ink-muted); }
	.small { font-size: .83rem; line-height: 1.5; color: var(--ink-soft); margin-top: .9rem; }
	table { border-collapse: collapse; width: 100%; text-align: left; font-variant-numeric: tabular-nums; }td, th { padding: .65rem .3rem; border-bottom: 1px solid var(--rule); font-weight: 400; }.metrics { table-layout: fixed; }.metrics th:first-child { width: 46%; padding-left: 0; }.metrics thead { font: .59rem var(--font-mono); color: var(--ink-soft); }.metrics tbody th { font-size: .82rem; }.metrics td { text-align: right; font: .8rem var(--font-mono); }.metrics thead th:not(:first-child) { text-align: right; }.active-column { color: var(--cobalt); }
	.reading-strip { padding: .9rem 1rem; display: flex; flex-wrap: wrap; align-items: baseline; gap: .5rem 1.25rem; border-top: 1px solid var(--rule); background: var(--paper-soft); }.reading-strip p { font-size: .87rem; color: var(--ink-soft); }
	.method-notes { display: grid; grid-template-columns: 1fr 1fr; gap: 2rem; }.method-notes h3 { margin-bottom: .5rem; }.method-notes p { color: var(--ink-soft); font-size: .88rem; line-height: 1.5; }
	pre { white-space: pre-wrap; overflow-wrap: anywhere; padding: 1rem; background: var(--paper-soft); max-height: 24rem; overflow: auto; font-size: .7rem; }
	.table-toolbar { padding: 1rem; display: flex; flex-wrap: wrap; align-items: center; gap: .75rem; border-top: 1px solid var(--rule); }.table-toolbar > span { margin-left: auto; }.allocation-table { overflow: auto; max-height: 25rem; padding: 0 1rem; font: .73rem var(--font-mono); }.allocation-table th, .allocation-table td { white-space: nowrap; }.allocation-table .chosen { background: var(--paper-soft); }.allocation-table button { min-height: 2.5rem; background: transparent; border: 0; font: inherit; text-align: left; color: var(--ink); cursor: pointer; text-decoration: underline; text-underline-offset: .2rem; }caption { text-align: left; color: var(--ink-soft); padding: .5rem 0; font-size: .68rem; }
	@media(max-width: 65rem) { .workbench { grid-template-columns: 1fr; }aside { border-left: 0; border-top: 1px solid var(--rule); }.metrics { max-width: 40rem; }.metrics thead { font-size: .7rem; }.inspector-section { margin-top: 1rem; padding-top: 1rem; } }
	@media(max-width: 42rem) { .experiment-strip { gap: 1rem 1.5rem; padding: .85rem .75rem; }.experiment-strip strong { font-size: 1.3rem; }.experiment-strip small { display: block; margin-top: .25rem; }.experiment-strip button { margin: 0; }aside { padding: 1rem; }.method-notes { grid-template-columns: 1fr; gap: 1.25rem; }.table-toolbar > span { margin-left: 0; }.view-note { padding: 0 .75rem .8rem; } }
</style>
