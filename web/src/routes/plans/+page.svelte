<script lang="ts">
	import { onMount } from 'svelte';
	import { scenarioStore } from '$lib/scenario.svelte';
	import { formatCurrency, formatPercent } from '$lib/format';
	import PlanTable from '$lib/components/PlanTable.svelte';

	onMount(() => {
		scenarioStore.ensureLoaded();
	});
</script>

<svelte:head>
	<title>Ginseng — Funding terminal</title>
</svelte:head>

{#if scenarioStore.response}
	{@const s = scenarioStore.response}
	{@const baseline = scenarioStore.baselineResponse}
	<div class="terminal-view">
		<header class="view-toolbar">
			<div><strong>Funding paths</strong><span>policy-ranked ways to close the active reserve gap</span></div>
			<p>{scenarioStore.request.obligations.length} scheduled events / {formatCurrency(s.funding_gap)} gap</p>
		</header>

		<div class="funding-layout">
			<section class="plan-console" aria-label="Funding plan comparison">
				<PlanTable plans={s.plans} recommendation={s.recommendation} />
			</section>

			<aside class="funding-inspector">
				<section>
					<p class="label">Current constraint</p>
					<strong class:attention={s.funding_gap > 0} class="inspector-value numeric">{formatCurrency(s.funding_gap)}</strong>
					<span>Gap to the reserve required by the active policy.</span>
				</section>
				<section>
					<p class="label">Scenario delta</p>
					{#if baseline}
						<div class="comparison"><span>Reserve</span><strong class="numeric">{formatCurrency(baseline.required_liquidity_reserve)} → {formatCurrency(s.required_liquidity_reserve)}</strong></div>
						<div class="comparison"><span>Shortfall chance</span><strong>{formatPercent(baseline.severity.cash_shortfall_probability)} → {formatPercent(s.severity.cash_shortfall_probability)}</strong></div>
					{:else}
						<span>Baseline contrast unavailable.</span>
					{/if}
				</section>
				<section>
					<p class="label">Reading the list</p>
					<span>Every option uses the same modeled paths. Differences reflect funding tradeoffs, not a different market draw.</span>
				</section>
			</aside>
		</div>
	</div>
{:else if scenarioStore.loadState === 'unreachable' || scenarioStore.loadState === 'error'}
	<div class="terminal-state" role="alert"><p>Local model unavailable</p><span>{scenarioStore.errorMessage}</span><button type="button" onclick={() => scenarioStore.refresh()}>Retry model</button></div>
{:else}
	<p class="terminal-loading" role="status" aria-live="polite">Ranking funding paths…</p>
{/if}

<style>
	.terminal-view {
		display: flex;
		flex-direction: column;
		height: calc(100dvh - 3rem);
		background: #050505;
		color: #e5e5e7;
	}
	.view-toolbar {
		flex: none;
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 1rem;
		min-height: 3.35rem;
		padding: 0 1rem;
		border-bottom: 1px solid #29292d;
		background: #0c0c0d;
	}
	.view-toolbar div { display: flex; align-items: baseline; gap: 0.6rem; }
	.view-toolbar strong { font-size: 0.86rem; letter-spacing: -0.02em; }
	.view-toolbar span, .view-toolbar p { color: #898990; font-family: var(--font-mono); font-size: 0.62rem; letter-spacing: 0.045em; text-transform: uppercase; }

	.funding-layout { flex: 1; min-height: 0; display: grid; grid-template-columns: minmax(0, 1fr) 18rem; }
	.plan-console { min-width: 0; min-height: 0; overflow-y: auto; padding: 1rem; border-right: 1px solid #29292d; }
	.funding-inspector { display: grid; align-content: start; min-height: 0; overflow-y: auto; background: #0b0b0c; }
	.funding-inspector section { display: grid; gap: 0.65rem; padding: 1rem; border-bottom: 1px solid #29292d; }
	.label { color: #88888e; font-family: var(--font-mono); font-size: 0.62rem; font-weight: 700; letter-spacing: 0.055em; text-transform: uppercase; }
	.inspector-value { font-size: 1.6rem; font-weight: 750; letter-spacing: -0.06em; }
	.inspector-value.attention { color: #ff7186; }
	.funding-inspector span { color: #9999a0; font-size: 0.73rem; line-height: 1.45; }
	.comparison { display: grid; gap: 0.18rem; }
	.comparison strong { color: #dedee1; font-size: 0.76rem; }

	.terminal-state, .terminal-loading {
		display: grid;
		place-content: center;
		gap: 0.5rem;
		min-height: calc(100dvh - 3rem);
		padding: 2rem;
		background: #050505;
		color: #a2a2a8;
		font-family: var(--font-mono);
		font-size: 0.72rem;
		text-transform: uppercase;
	}
	.terminal-state p { color: #ff7186; }
	.terminal-state span { max-width: 44ch; font-family: var(--font-sans); font-size: 0.82rem; text-transform: none; }
	.terminal-state button {
		justify-self: start;
		min-height: 2.3rem;
		padding: 0 0.7rem;
		background: #18181a;
		border: 1px solid #55555c;
		color: #fff;
		font: inherit;
		cursor: pointer;
	}

	@media (max-width: 56rem) {
		.terminal-view { height: auto; min-height: calc(100dvh - 3rem); }
		.funding-layout { flex: none; grid-template-columns: 1fr; }
		.plan-console, .funding-inspector { overflow-y: visible; }
		.plan-console { border-right: 0; }
		.funding-inspector { grid-template-columns: repeat(3, minmax(0, 1fr)); border-top: 1px solid #29292d; }
		.funding-inspector section { min-width: 0; border-right: 1px solid #29292d; border-bottom: 0; }
	}

	@media (max-width: 42rem) {
		.view-toolbar { display: grid; align-items: center; gap: 0.2rem; padding: 0.6rem 0.75rem; }
		.view-toolbar div { display: grid; gap: 0.2rem; }
		.view-toolbar p { margin: 0; }
		.plan-console { padding: 0.65rem; }
		.funding-inspector { grid-template-columns: 1fr; }
		.funding-inspector section { border-right: 0; border-bottom: 1px solid #29292d; }
	}
</style>
