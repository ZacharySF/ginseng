<script lang="ts">
	import NumericalRiskPanel from '$lib/components/NumericalRiskPanel.svelte';
	import { onMount } from 'svelte';
	import { scenarioStore } from '$lib/scenario.svelte';
	import { formatCurrency, formatPercent } from '$lib/format';
	import CashPathChart from '$lib/components/CashPathChart.svelte';
	import ScenarioComposer from '$lib/components/ScenarioComposer.svelte';

	onMount(() => {
		scenarioStore.ensureLoaded();
	});

	const chartEvents = $derived(
		scenarioStore.request.obligations.map((obligation) => ({
			id: obligation.id,
			label: obligation.label,
			amount: obligation.amount,
			day: obligation.due_in_days,
			kind: 'outflow' as const
		}))
	);
</script>

<svelte:head>
	<title>Ginseng — Synthetic events demo</title>
	<meta
		name="description"
		content="Edit a synthetic future-cost scenario and inspect its modeled cash consequences without using personal balances or bills."
	/>
</svelte:head>

{#if scenarioStore.response}
	{@const s = scenarioStore.response}
	<div class="terminal-view">
		<header class="view-toolbar">
			<div><strong>Synthetic event editor</strong><span>schedule simulated commitments against the active demo cash path</span></div>
			<p>{scenarioStore.request.paths.toLocaleString()} modeled demo paths</p>
		</header>

		<div class="event-layout">
			<section class="composer-pane"><ScenarioComposer /></section>
			<main class="chart-pane">
				<section class="simulation" aria-labelledby="cash-path-title">
					<div class="section-heading"><div><p class="label">Synthetic cash-path simulation</p><h1 id="cash-path-title">Projected demo cash</h1></div><span>This synthetic scenario stays separate from your saved personal balances and bills.</span></div>
					<CashPathChart cashPaths={s.cash_paths} operatingBuffer={s.operating_buffer} events={chartEvents} asOf={s.as_of} />
				</section>
				<section class="scenario-read" aria-label="Current synthetic scenario read">
					<div><p class="label">Funding gap</p><strong class:attention={s.funding_gap > 0} class="numeric">{formatCurrency(s.funding_gap)}</strong><span>Required to satisfy the active reserve policy.</span></div>
					<div><p class="label">Shortfall chance</p><strong class:attention={s.severity.cash_shortfall_probability > 0} class="numeric">{formatPercent(s.severity.cash_shortfall_probability)}</strong><span>Modeled paths falling below zero.</span></div>
					<div><p class="label">Required reserve</p><strong class="numeric">{formatCurrency(s.required_liquidity_reserve)}</strong><span>Liquid reserve at the chosen coverage target.</span></div>
				</section>
			</main>
		</div>
        {#key JSON.stringify(scenarioStore.request)}
            <NumericalRiskPanel request={scenarioStore.request} endpoint="/demo/numerics" supported={scenarioStore.loadState === 'ready' && !scenarioStore.request.drought_view && scenarioStore.request.horizon_days <= 60} />
        {/key}
	</div>
{:else if scenarioStore.loadState === 'unreachable' || scenarioStore.loadState === 'error'}
	<div class="terminal-state" role="alert"><p>Local model unavailable</p><span>{scenarioStore.errorMessage}</span><button type="button" onclick={() => scenarioStore.refresh()}>Retry model</button></div>
{:else}
	<p class="terminal-loading" role="status" aria-live="polite">Building synthetic future cash paths…</p>
{/if}

<style>
	.terminal-view {
		display: flex;
		flex-direction: column;
		min-height: calc(100dvh - 3.25rem);
		background: var(--paper);
		color: var(--ink);
	}

	.view-toolbar {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 1rem;
		min-height: 3.35rem;
		padding: 0.3rem 1rem;
		background: var(--paper);
		border-bottom: 1px solid var(--rule);
	}

	.view-toolbar div,
	.section-heading {
		display: flex;
		align-items: baseline;
		justify-content: space-between;
		gap: 0.8rem;
	}

	.view-toolbar div,
	.section-heading > div {
		min-width: 0;
	}

	.view-toolbar strong {
		font-size: 0.9rem;
		letter-spacing: -0.02em;
	}

	.view-toolbar span,
	.view-toolbar p,
	.label {
		margin: 0;
		color: var(--ink-soft);
		font-family: var(--font-mono);
		font-size: 0.63rem;
		font-weight: 700;
		letter-spacing: 0.055em;
		text-transform: uppercase;
	}

	.event-layout {
		flex: 1;
		display: grid;
		grid-template-columns: minmax(23rem, 0.9fr) minmax(0, 1.1fr);
		min-height: 0;
	}

	.composer-pane {
		min-height: 0;
		padding: 1rem;
		overflow-y: auto;
		background: var(--paper-soft);
		border-right: 1px solid var(--rule);
	}

	.chart-pane {
		display: grid;
		grid-template-rows: minmax(0, 1fr) auto;
		min-width: 0;
		min-height: 0;
	}

	.simulation {
		display: flex;
		flex-direction: column;
		min-width: 0;
		min-height: 0;
		padding: 1rem;
	}

	.simulation :global(.cash-path-chart) {
		flex: 1;
		min-height: 0;
	}

	.section-heading {
		flex: none;
		align-items: end;
		margin-bottom: 0.85rem;
	}

	.section-heading > div {
		display: grid;
		gap: 0.2rem;
	}

	.section-heading h1 {
		font-size: 1.05rem;
		letter-spacing: -0.03em;
		line-height: 1.1;
	}

	.section-heading > span {
		max-width: 34ch;
		color: var(--ink-soft);
		font-size: 0.74rem;
		line-height: 1.35;
		text-align: right;
	}

	.scenario-read {
		display: grid;
		grid-template-columns: repeat(3, minmax(0, 1fr));
		gap: 1px;
		background: var(--rule);
		border-top: 1px solid var(--rule);
	}

	.scenario-read > div {
		display: grid;
		gap: 0.4rem;
		padding: 0.85rem 1rem;
		background: var(--paper-deep);
	}

	.scenario-read strong {
		color: var(--ink);
		font-size: 1.05rem;
		letter-spacing: -0.04em;
	}

	.scenario-read strong.attention,
	.terminal-state p {
		color: var(--negative);
	}

	.scenario-read span,
	.terminal-state,
	.terminal-loading {
		color: var(--ink-soft);
	}

	.scenario-read span {
		font-size: 0.7rem;
		line-height: 1.35;
	}

	.terminal-state,
	.terminal-loading {
		display: grid;
		place-content: center;
		gap: 0.5rem;
		min-height: calc(100dvh - 3.25rem);
		padding: 2rem;
		background: var(--paper);
		font-family: var(--font-mono);
		font-size: 0.72rem;
		text-transform: uppercase;
	}

	.terminal-state span {
		max-width: 44ch;
		font-family: var(--font-sans);
		font-size: 0.82rem;
		text-transform: none;
	}

	.terminal-state button {
		justify-self: start;
		min-height: 2.75rem;
		padding: 0 0.75rem;
		background: var(--cobalt);
		border: 1px solid var(--cobalt);
		color: var(--paper);
		font: inherit;
		cursor: pointer;
	}

	@media (max-width: 65rem) {
		.event-layout {
			grid-template-columns: 1fr;
		}

		.composer-pane {
			border-right: 0;
			border-bottom: 1px solid var(--rule);
			overflow-y: visible;
		}

		.chart-pane {
			min-height: 34rem;
		}
	}

	@media (max-width: 42rem) {
		.view-toolbar,
		.section-heading {
			display: grid;
			align-items: start;
			gap: 0.25rem;
			padding: 0.6rem 0.75rem;
		}

		.section-heading {
			padding: 0;
		}

		.view-toolbar div {
			display: grid;
			gap: 0.2rem;
		}

		.composer-pane,
		.simulation {
			padding: 0.75rem;
		}

		.section-heading > span {
			max-width: none;
			text-align: left;
		}

		.scenario-read {
			grid-template-columns: 1fr;
		}
	}
</style>
