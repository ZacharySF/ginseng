<script lang="ts">
	import { onMount } from 'svelte';
	import CashWorkbench from '$lib/components/CashWorkbench.svelte';
	import { scenarioStore } from '$lib/scenario.svelte';

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
	<title>Ginseng — Synthetic cash example</title>
	<meta
		name="description"
		content="Explore an explicit synthetic cash example without changing personal balances, bills, or inputs."
	/>
</svelte:head>

{#if scenarioStore.loadState === 'loading' && !scenarioStore.response}
	<div class="terminal-state" role="status" aria-live="polite"><p>Loading the synthetic cash projection…</p></div>
{:else if scenarioStore.loadState === 'unreachable' || scenarioStore.loadState === 'error'}
	<div class="terminal-state terminal-state--error" role="alert"><p>Simulated model unavailable</p><span>{scenarioStore.errorMessage}</span><button type="button" onclick={() => scenarioStore.refresh()}>Retry demo model</button></div>
{:else if scenarioStore.response}
	<CashWorkbench
		response={scenarioStore.response}
		events={chartEvents}
		source="demo"
		horizonDays={scenarioStore.request.horizon_days}
		modelMode="demo"
		onHorizonChange={(horizon) => scenarioStore.setHorizonDays(horizon)}
		eventsHref="/demo/future"
		reserveHref="/demo/liquidity"
		fundingHref="/demo/plans"
		paths={scenarioStore.request.paths}
		isPreview={!scenarioStore.isBaseline}
		updating={scenarioStore.loadState === 'loading'}
	/>
{/if}

<style>
	.terminal-state { display:grid; place-content:center; gap:.6rem; min-height:calc(100dvh - 3rem); padding:2rem; background:var(--paper); color:var(--ink-soft); font-family:var(--font-mono); font-size:.75rem; letter-spacing:.04em; text-transform:uppercase; }.terminal-state--error { place-content:center start; color:var(--negative); }.terminal-state--error span { max-width:48ch; color:var(--ink-soft); font-family:var(--font-sans); font-size:.875rem; letter-spacing:0; text-transform:none; }.terminal-state button { justify-self:start; min-height:2.75rem; padding:0 .75rem; background:var(--cobalt); border:1px solid var(--cobalt); color:var(--paper); font:inherit; font-size:.68rem; cursor:pointer; }</style>
