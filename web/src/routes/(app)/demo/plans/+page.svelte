<script lang="ts">
    import FundingLimits from '$lib/components/FundingLimits.svelte';
    import FundingAnalysisPanel from '$lib/components/FundingAnalysisPanel.svelte';
    import PortfolioAnalysisPanel from '$lib/components/PortfolioAnalysisPanel.svelte';

	import { onMount } from 'svelte';
	import FundingWorkbench from '$lib/components/FundingWorkbench.svelte';
	import { scenarioStore } from '$lib/scenario.svelte';

	onMount(() => {
		scenarioStore.ensureLoaded();
	});
</script>

<svelte:head>
	<title>Ginseng — Synthetic funding demo</title>
	<meta name="description" content="Inspect funding tradeoffs in a synthetic scenario that remains separate from personal financial data." />
</svelte:head>

{#if scenarioStore.response}
	<FundingWorkbench
        updating={scenarioStore.loadState === 'loading'}
        onRetry={() => void scenarioStore.refresh()}
        onLoadExample={() => scenarioStore.loadRepairExample()}
		response={scenarioStore.response}
		baseline={scenarioStore.baselineResponse}
		comparisonLabel="synthetic baseline"
		source="demo"
		modelMode="demo"
		isPreview={!scenarioStore.isBaseline}
		eventsHref="/demo/future"
	/>
<FundingLimits />
    <FundingAnalysisPanel />
    <PortfolioAnalysisPanel />
{:else if scenarioStore.loadState === 'unreachable' || scenarioStore.loadState === 'error'}
	<div class="terminal-state" role="alert"><p>Local model unavailable</p><span>{scenarioStore.errorMessage}</span><button type="button" onclick={() => scenarioStore.refresh()}>Retry model</button></div>
{:else}
	<p class="terminal-loading" role="status" aria-live="polite">Ranking synthetic funding paths…</p>
{/if}

<style>
	.terminal-state,.terminal-loading { display:grid; place-content:center; gap:.5rem; min-height:calc(100dvh - 3rem); padding:2rem; background:var(--paper); color:var(--ink-soft); font-family:var(--font-mono); font-size:.72rem; text-transform:uppercase; }.terminal-state p { color:var(--negative); }.terminal-state span { max-width:44ch; color:var(--ink-soft); font-family:var(--font-sans); font-size:.82rem; text-transform:none; }.terminal-state button { justify-self:start; min-height:2.75rem; padding:0 .75rem; background:var(--cobalt); border:1px solid var(--cobalt); color:var(--paper); font:inherit; cursor:pointer; }
</style>
