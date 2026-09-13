<script lang="ts">
	import { onMount } from 'svelte';
	import { scenarioStore } from '$lib/scenario.svelte';
	import { formatCurrency, formatPercent } from '$lib/format';
	import CashPathChart from '$lib/components/CashPathChart.svelte';
	import ScenarioComposer from '$lib/components/ScenarioComposer.svelte';

	onMount(() => {
		scenarioStore.ensureLoaded();
	});
</script>

<svelte:head>
	<title>Ginseng — Events terminal</title>
	<meta name="description" content="Build an editable future-cost scenario and inspect its modeled cash consequences." />
</svelte:head>

{#if scenarioStore.response}
	{@const s = scenarioStore.response}
	<div class="terminal-view">
		<header class="view-toolbar">
			<div><strong>Event ledger</strong><span>schedule commitments against the active cash path</span></div>
			<p>{scenarioStore.request.paths.toLocaleString()} modeled paths</p>
		</header>

		<div class="event-layout">
			<section class="composer-pane"><ScenarioComposer /></section>
			<main class="chart-pane">
				<section class="simulation" aria-labelledby="cash-path-title">
					<div class="section-heading"><div><p class="label">Cash-path simulation</p><h1 id="cash-path-title">Projected available cash</h1></div><span>Median line, middle 80% field, operating buffer, and scheduled event markers.</span></div>
					<CashPathChart cashPaths={s.cash_paths} operatingBuffer={s.operating_buffer} obligations={scenarioStore.request.obligations} />
				</section>
				<section class="scenario-read" aria-label="Current scenario read">
					<div><p class="label">Funding gap</p><strong class:attention={s.funding_gap > 0} class="numeric">{formatCurrency(s.funding_gap)}</strong><span>Required to satisfy the active reserve policy.</span></div>
					<div><p class="label">Shortfall chance</p><strong class:attention={s.severity.cash_shortfall_probability > 0} class="numeric">{formatPercent(s.severity.cash_shortfall_probability)}</strong><span>Modeled paths falling below zero.</span></div>
					<div><p class="label">Required reserve</p><strong class="numeric">{formatCurrency(s.required_liquidity_reserve)}</strong><span>Liquid reserve at the chosen coverage target.</span></div>
				</section>
			</main>
		</div>
	</div>
{:else if scenarioStore.loadState === 'unreachable' || scenarioStore.loadState === 'error'}
	<div class="terminal-state" role="alert"><p>Local model unavailable</p><span>{scenarioStore.errorMessage}</span><button type="button" onclick={() => scenarioStore.refresh()}>Retry model</button></div>
{:else}
	<p class="terminal-loading" role="status" aria-live="polite">Building future cash paths…</p>
{/if}

<style>
	.terminal-view { display:flex; flex-direction:column; height:calc(100dvh - 3rem); background:#050505; color:#e5e5e7; }.view-toolbar { flex:none; display:flex; align-items:center; justify-content:space-between; gap:1rem; min-height:3.35rem; padding:0 1rem; border-bottom:1px solid #29292d; background:#0c0c0d; }.view-toolbar div { display:flex; align-items:baseline; gap:.6rem; }.view-toolbar strong { font-size:.86rem; letter-spacing:-.02em; }.view-toolbar span,.view-toolbar p,.label { color:#898990; font-family:var(--font-mono); font-size:.62rem; font-weight:700; letter-spacing:.055em; text-transform:uppercase; }
	.event-layout { flex:1; min-height:0; display:grid; grid-template-columns:minmax(24rem, 1fr) minmax(0,1.1fr); }.composer-pane { min-height:0; overflow-y:auto; padding:1rem; border-right:1px solid #29292d; background:#0a0a0b; }.chart-pane { display:grid; grid-template-rows:minmax(0,1fr) auto; min-width:0; min-height:0; }.simulation { display:flex; flex-direction:column; min-width:0; min-height:0; padding:1rem; overflow:hidden; }.simulation :global(.cash-path-chart) { flex:1; min-height:0; }.section-heading { flex:none; display:flex; justify-content:space-between; gap:1rem; margin-bottom:.85rem; }.section-heading div { display:grid; gap:.25rem; }.section-heading h1 { margin:0; color:#e5e5e7; font-size:.94rem; letter-spacing:-.02em; }.section-heading > span { max-width:37ch; color:#96969c; font-size:.72rem; line-height:1.4; }
	.scenario-read { display:grid; grid-template-columns:repeat(3,1fr); gap:1px; border-top:1px solid #29292d; background:#29292d; }.scenario-read > div { display:grid; gap:.4rem; padding:.85rem 1rem; background:#0d0d0e; }.scenario-read strong { color:#e0e0e3; font-size:1.05rem; letter-spacing:-.04em; }.scenario-read strong.attention { color:#ff7186; }.scenario-read span { color:#919197; font-size:.7rem; line-height:1.35; }
	.terminal-state,.terminal-loading { display:grid; place-content:center; gap:.5rem; height:calc(100dvh - 3rem); padding:2rem; background:#050505; color:#a2a2a8; font-family:var(--font-mono); font-size:.72rem; text-transform:uppercase; }.terminal-state p { color:#ff7186; }.terminal-state span { max-width:44ch; font-family:var(--font-sans); font-size:.82rem; text-transform:none; }.terminal-state button { justify-self:start; min-height:2.3rem; padding:0 .7rem; background:#18181a; border:1px solid #55555c; color:#fff; font:inherit; cursor:pointer; }
	@media(max-width:65rem){.terminal-view{height:auto;min-height:calc(100dvh - 3rem);}.event-layout{grid-template-columns:1fr;flex:none;}.composer-pane{border-right:0;border-bottom:1px solid #29292d;overflow-y:visible;}.chart-pane{min-height:34rem}}@media(max-width:42rem){.view-toolbar{display:grid;gap:.2rem;padding:.6rem .75rem}.view-toolbar div{display:grid;gap:.2rem}.view-toolbar p{margin:0}.composer-pane,.simulation{padding:.75rem}.section-heading{display:grid}.scenario-read{grid-template-columns:1fr}}
	/* Cobalt ledger skin */
	.terminal-view { background: var(--paper); color: var(--ink); }
	.view-toolbar { background: var(--paper); border-color: var(--rule); }
	.view-toolbar span, .view-toolbar p, .label { color: var(--ink-muted); }
	.composer-pane { background: var(--paper-soft); border-color: var(--rule); }
	.section-heading h1 { color: var(--ink); }
	.section-heading > span { color: var(--ink-muted); }
	.scenario-read { background: var(--rule); border-color: var(--rule); }
	.scenario-read > div { background: var(--paper-deep); }
	.scenario-read strong { color: var(--ink); }
	.scenario-read strong.attention, .terminal-state p { color: var(--negative); }
	.scenario-read span, .terminal-state, .terminal-loading { color: var(--ink-muted); }
	.terminal-state, .terminal-loading { background: var(--paper); }
	.terminal-state button { background: var(--cobalt); border-color: var(--cobalt); color: var(--on-accent); }
</style>
