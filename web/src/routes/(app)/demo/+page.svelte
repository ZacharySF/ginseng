<script lang="ts">
	import { onMount } from 'svelte';
	import { scenarioStore } from '$lib/scenario.svelte';
	import CashWorkbench from '$lib/components/CashWorkbench.svelte';

	onMount(() => {
		scenarioStore.ensureLoaded();
	});
</script>

<svelte:head>
	<title>Ginseng — Simulated cash workspace</title>
	<meta
		name="description"
		content="A simulated local cash-account workspace for scenario timing, balance paths, and reserve decisions."
	/>
</svelte:head>

{#if scenarioStore.loadState === 'loading' && !scenarioStore.response}
	<div class="terminal-state" role="status" aria-live="polite">
		<p>Loading simulated local account projection…</p>
	</div>
{:else if scenarioStore.loadState === 'unreachable' || scenarioStore.loadState === 'error'}
	<div class="terminal-state terminal-state--error" role="alert">
		<p>Simulated model unavailable</p>
		<span>{scenarioStore.errorMessage}</span>
		<button type="button" onclick={() => scenarioStore.refresh()}>Retry demo model</button>
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
		background: var(--paper);
		color: var(--ink-muted);
		font-family: var(--font-mono);
		font-size: 0.75rem;
		letter-spacing: 0.04em;
		text-transform: uppercase;
	}

	.terminal-state--error {
		place-content: center start;
		color: var(--negative);
	}

	.terminal-state--error span {
		max-width: 48ch;
		color: var(--ink-soft);
		font-family: var(--font-sans);
		font-size: 0.875rem;
		letter-spacing: 0;
		text-transform: none;
	}

	.terminal-state button {
		justify-self: start;
		min-height: 2.75rem;
		padding: 0 0.75rem;
		background: var(--cobalt);
		border: 1px solid var(--cobalt);
		color: var(--on-accent);
		font: inherit;
		font-size: 0.68rem;
		cursor: pointer;
	}
</style>
