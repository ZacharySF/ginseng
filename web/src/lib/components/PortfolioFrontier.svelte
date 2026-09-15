<script lang="ts">
	import type { FrontierReady } from '$lib/frontier-types';
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

<section class="frontier-results" aria-label="Portfolio frontier research results">
	<div class="experiment-strip">
		<div><strong>{report.points.length}</strong><span>allocations explored</span></div>
		<div><strong>{frontier.length}</strong><span>discovery Pareto candidates</span></div>
		<div><strong>{report.pressure.discovery_count} / {report.pressure.evaluation_count}</strong><span>pressure paths · discovery / check</span></div>
		<button onclick={download}>Export experiment JSON ↗</button>
	</div>
	<div class="view-controls">
		<div class="tabs" aria-label="Evaluation sample">
			<button class:active={view === 'discovery'} aria-pressed={view === 'discovery'} onclick={() => view = 'discovery'}>Discovery sample</button>
			<button class:active={view === 'evaluation'} aria-pressed={view === 'evaluation'} onclick={() => view = 'evaluation'}>Fresh-sample check</button>
		</div>
		<label><input type="checkbox" bind:checked={frontierOnly}/> Focus on Pareto candidates</label>
	</div>
	<p class="view-note">{view === 'discovery' ? 'Each point is a fully invested allocation. Blue points have no explored alternative that is at least as good on all three objectives and strictly better on one.' : 'The weights and blue discovery labels stay fixed. Only the simulated futures change. The selected line connects its discovery and fresh-sample estimates.'}</p>
	<div class="workbench">
		<FrontierChart {report} selectedId={selected.id} {view} {frontierOnly} onSelect={id => selectedId = id}/>
		<aside aria-label="Selected allocation details">
			<p class="eyebrow">Allocation inspector</p>
			<label for="allocation-select">Select a portfolio</label>
			<select id="allocation-select" value={selected.id} onchange={event => selectedId = event.currentTarget.value}>
				{#each report.points as point}<option value={point.id}>{point.label}{point.pareto ? ' · Pareto' : ''}</option>{/each}
			</select>
			<div class="point-status"><span>{selected.source}</span><span>{selected.pareto ? 'Discovery Pareto set' : 'Outside discovery Pareto set'}</span></div>
			<h3>Capital allocation</h3>
			{#each report.symbols as symbol, index}
				<div class="weight-row"><div><strong>{symbol}</strong><span>{pct(selected.weights[index])}</span></div><div class="weight-track"><span style:width={`${selected.weights[index] * 100}%`}></span></div></div>
			{/each}
			<p class="small">CASH is a hypothetical portfolio sleeve with zero modeled yield. It does not add money to the bank account or change when cash pressure occurs.</p>
			<h3>Same weights, independent samples</h3>
			<table class="metrics"><thead><tr><th>Objective</th><th>Discovery</th><th>Check</th></tr></thead><tbody>
				<tr><th>Expected return ↑</th><td>{pct(selected.discovery.mean_return)}</td><td>{pct(selected.evaluation.mean_return)}</td></tr>
				<tr><th>Volatility ↓</th><td>{pct(selected.discovery.volatility)}</td><td>{pct(selected.evaluation.volatility)}</td></tr>
				<tr><th>Pressure tail loss ↓</th><td>{pct(selected.discovery.pressure_cvar)}</td><td>{pct(selected.evaluation.pressure_cvar)}</td></tr>
			</tbody></table>
			<p class="small">Return and volatility cover the forecast horizon, without annualization. Tail loss averages the worst 5% within first-breach paths; a negative value denotes a gain.</p>
		</aside>
	</div>
	<div class="method-notes">
		<div><h3>Why the third axis matters</h3><p>Ordinary volatility measures how widely returns vary. Cash-pressure tail loss measures the portfolio loss when bank cash first falls below its operating buffer. Similar risk/return profiles can have different behavior at that moment.</p></div>
		<div><h3>What the check establishes</h3><p>Fresh simulations probe numerical stability under the same historical model. They are not a future-period backtest. The Pareto label is relative to the explored candidate set, not proof of a complete global frontier.</p></div>
	</div>
	<details><summary>Sampling and optimization record</summary><p class="small">The worst 5% contains {report.pressure.discovery_tail_mass_count.toFixed(1)} scenario-equivalents in discovery and {report.pressure.evaluation_tail_mass_count.toFixed(1)} in the check, including fractional boundary observations. Small differences can be sensitive to a few scenarios.</p><pre>{JSON.stringify(report.metadata, null, 2)}</pre></details>
	<button class="table-toggle" aria-expanded={showTable} onclick={() => showTable = !showTable}>{showTable ? 'Hide' : 'Show'} all allocation values</button>
	{#if showTable}<div class="allocation-table"><table><caption>{view === 'discovery' ? 'Discovery sample' : 'Fresh-sample check'} · all horizon returns and risks in percent</caption><thead><tr><th>Allocation</th><th>Return ↑</th><th>Volatility ↓</th><th>Pressure tail loss ↓</th><th>Discovery set</th></tr></thead><tbody>
		{#each report.points as point}<tr><th><button onclick={() => selectedId = point.id}>{point.label}</button></th><td>{pct(point[view].mean_return)}</td><td>{pct(point[view].volatility)}</td><td>{pct(point[view].pressure_cvar)}</td><td>{point.pareto ? 'Pareto' : 'Other'}</td></tr>{/each}
	</tbody></table></div>{/if}
</section>
<style>
	.frontier-results { border: 1px solid var(--rule); background: var(--paper); min-width: 0; }
	.experiment-strip { display: flex; align-items: center; flex-wrap: wrap; gap: 1.5rem; padding: 1rem 1.2rem; background: var(--paper-soft); border-bottom: 1px solid var(--rule); }
	.experiment-strip > div { display: grid; gap: .25rem; }.experiment-strip strong { font-size: 1.45rem; }.experiment-strip span { font-size: .65rem; font-family: var(--font-mono); color: var(--ink-soft); }.experiment-strip button { margin-left: auto; }
	button, select { min-height: 2.6rem; font: inherit; background: var(--paper); border: 1px solid var(--control-border); color: var(--ink); padding: .4rem .75rem; cursor: pointer; }
	.view-controls { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 1rem; padding: 1rem 1.2rem .5rem; }.tabs { display: flex; gap: .3rem; }.active { background: var(--cobalt); color: var(--on-accent); border-color: var(--cobalt); }
	.view-controls label { display: flex; align-items: center; gap: .4rem; font-size: .85rem; }input { accent-color: var(--cobalt); }
	.view-note { padding: .5rem 1.2rem 1rem; color: var(--ink-soft); font-size: .85rem; border-bottom: 1px solid var(--rule); }
	.workbench { display: grid; grid-template-columns: minmax(0, 1fr) minmax(18rem, .48fr); }aside { padding: 1.2rem; border-left: 1px solid var(--rule); background: var(--paper-soft); min-width: 0; }
	.eyebrow { font: .65rem var(--font-mono); letter-spacing: .06em; text-transform: uppercase; color: var(--ink-soft); margin-bottom: .8rem; }aside label { display: block; margin-bottom: .4rem; }select { width: 100%; }
	.point-status { display: flex; flex-wrap: wrap; gap: .4rem; margin: .6rem 0 1.2rem; font: .6rem var(--font-mono); color: var(--ink-soft); }.point-status span { padding: .3rem; border: 1px solid var(--rule); }
	h3 { font-size: 1rem; margin-bottom: .6rem; }.weight-row { margin: .75rem 0; }.weight-row > div:first-child { display: flex; justify-content: space-between; font: .75rem var(--font-mono); margin-bottom: .35rem; }.weight-track { height: .3rem; background: var(--rule); }.weight-track span { display: block; height: 100%; background: var(--cobalt); }
	.small { font-size: .8rem; color: var(--ink-soft); line-height: 1.45; margin: 1rem 0; }table { border-collapse: collapse; width: 100%; text-align: left; font-family: var(--font-mono); font-size: .7rem; }td, th { padding: .6rem .3rem; border-bottom: 1px solid var(--rule); font-weight: 400; }.metrics { font-size: .64rem; }.metrics th:first-child { width: 44%; }
	.method-notes { display: grid; grid-template-columns: 1fr 1fr; gap: 2rem; padding: 1.2rem; border-block: 1px solid var(--rule); }.method-notes p { font-size: .9rem; line-height: 1.45; color: var(--ink-soft); }
	details { padding: 1rem 1.2rem; border-bottom: 1px solid var(--rule); }summary { cursor: pointer; }pre { white-space: pre-wrap; overflow-wrap: anywhere; padding: 1rem; background: var(--paper-soft); max-height: 24rem; overflow: auto; font-size: .7rem; }.table-toggle { margin: 1rem 1.2rem; }.allocation-table { overflow: auto; max-height: 25rem; padding: 0 1.2rem; }caption { text-align: left; color: var(--ink-soft); padding: .5rem 0; }.allocation-table button { font-size: .7rem; text-align: left; }
	@media(max-width: 65rem) { .workbench { grid-template-columns: 1fr; }aside { border-left: 0; border-top: 1px solid var(--rule); }.metrics { font-size: .75rem; } }
	@media(max-width: 42rem) { .experiment-strip { gap: 1rem; }.experiment-strip button { margin: 0; }.tabs button { padding: .4rem .55rem; font-size: .85rem; }.method-notes { grid-template-columns: 1fr; gap: 1rem; }.experiment-strip, aside, .view-controls { padding: .85rem; } }
</style>
