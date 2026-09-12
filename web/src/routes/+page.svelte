<script lang="ts">
	import { onMount } from 'svelte';
	import { scenarioStore } from '$lib/scenario.svelte';
	import CashWorkbench from '$lib/components/CashWorkbench.svelte';

	onMount(() => {
		scenarioStore.ensureLoaded();
	});
</script>

<svelte:head>
	<title>Ginseng — Cash workspace</title>
	<meta
		name="description"
		content="An interactive local cash-account workspace for scenario timing, balance paths, and reserve decisions."
	/>
</svelte:head>

{#if scenarioStore.loadState === 'loading' && !scenarioStore.response}
	<div class="terminal-state" role="status" aria-live="polite">
		<p>Loading local account projection…</p>
	</div>
{:else if scenarioStore.loadState === 'unreachable' || scenarioStore.loadState === 'error'}
	<div class="terminal-state terminal-state--error" role="alert">
		<p>Local model unavailable</p>
		<span>{scenarioStore.errorMessage}</span>
		<button type="button" onclick={() => scenarioStore.refresh()}>Retry model</button>
	</div>
{:else if scenarioStore.response}
	<CashWorkbench response={scenarioStore.response} obligations={scenarioStore.request.obligations} />
{/if}

<style>
	.terminal-state {
		display: grid;
		place-content: center;
		gap: 0.6rem;
		min-height: calc(100dvh - 3rem);
		padding: 2rem;
		background: #050505;
		color: #aaaab0;
		font-family: var(--font-mono);
		font-size: 0.75rem;
		letter-spacing: 0.04em;
		text-transform: uppercase;
	}

	.terminal-state--error {
		place-content: center start;
		color: #ff7487;
	}

	.terminal-state--error span {
		max-width: 48ch;
		color: #a0a0a6;
		font-family: var(--font-sans);
		font-size: 0.875rem;
		letter-spacing: 0;
		text-transform: none;
	}

	.terminal-state button {
		justify-self: start;
		min-height: 2.4rem;
		padding: 0 0.75rem;
		background: #18181a;
		border: 1px solid #525258;
		border-radius: 0.25rem;
		color: #f4f4f5;
		font: inherit;
		font-size: 0.68rem;
		cursor: pointer;
	}
</style>
