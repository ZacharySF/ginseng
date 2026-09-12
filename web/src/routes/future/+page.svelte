<script lang="ts">
	import { onMount } from 'svelte';
	import { scenarioStore } from '$lib/scenario.svelte';
	import CashPathChart from '$lib/components/CashPathChart.svelte';

	onMount(() => {
		scenarioStore.ensureLoaded();
	});
</script>

<svelte:head>
	<title>Ginseng — Future</title>
</svelte:head>

{#if scenarioStore.response}
	{@const s = scenarioStore.response}
	<div class="future-screen">
		<header class="screen-header">
			<h1 class="screen-title">Future</h1>
			<p class="screen-subtitle">
				The distribution of upcoming cash paths under {scenarioStore.request.paths.toLocaleString()}
				simulated futures.
			</p>
		</header>

		<section class="shock-controls" aria-label="Shock control">
			<button
				type="button"
				class="shock-button"
				onclick={() => scenarioStore.applyShock()}
				disabled={scenarioStore.hasShock}
			>
				Insert $4,500 emergency repair
			</button>
			<button
				type="button"
				class="reset-button"
				onclick={() => scenarioStore.reset()}
				disabled={scenarioStore.isBaseline}
			>
				Reset to baseline
			</button>
			{#if scenarioStore.loadState === 'loading'}
				<span class="updating" role="status" aria-live="polite">Updating…</span>
			{/if}
		</section>

		<section class="chart-card" aria-label="Cash path chart">
			<CashPathChart
				cashPaths={s.cash_paths}
				operatingBuffer={s.operating_buffer}
				obligations={scenarioStore.request.obligations}
			/>
		</section>
	</div>
{:else if scenarioStore.loadState === 'unreachable' || scenarioStore.loadState === 'error'}
	<div class="engine-down" role="alert">
		<p class="engine-down-title">Engine unavailable</p>
		<p class="engine-down-detail">{scenarioStore.errorMessage}</p>
		<button type="button" class="retry-button" onclick={() => scenarioStore.refresh()}>Retry</button>
	</div>
{:else}
	<p class="status-text" role="status" aria-live="polite">Loading your future cash paths…</p>
{/if}

<style>
	.future-screen {
		display: flex;
		flex-direction: column;
		gap: var(--space-6);
	}

	.screen-header {
		display: flex;
		flex-direction: column;
		gap: var(--space-2);
	}

	.screen-title {
		font-size: var(--font-size-xl);
		font-weight: 700;
	}

	.screen-subtitle {
		color: var(--color-text-dim);
		font-size: var(--font-size-md);
		max-width: 56ch;
	}

	.shock-controls {
		display: flex;
		align-items: center;
		gap: var(--space-4);
		flex-wrap: wrap;
	}

	.shock-button,
	.reset-button {
		padding: var(--space-3) var(--space-5);
		border-radius: var(--radius-sm);
		font-size: var(--font-size-sm);
		font-weight: 600;
		cursor: pointer;
	}

	.shock-button {
		background: var(--color-danger);
		border: 1px solid var(--color-danger);
		color: var(--color-bg);
	}

	.shock-button:hover:not(:disabled) {
		background: color-mix(in srgb, var(--color-danger) 85%, white);
	}

	.reset-button {
		background: transparent;
		border: 1px solid var(--color-border-strong);
		color: var(--color-text);
	}

	.reset-button:hover:not(:disabled) {
		background: var(--color-bg-card-hover);
	}

	.shock-button:disabled,
	.reset-button:disabled {
		opacity: 0.45;
		cursor: not-allowed;
	}

	.shock-button:focus-visible,
	.reset-button:focus-visible {
		outline: 2px solid var(--color-accent);
		outline-offset: 2px;
	}

	.updating {
		font-size: var(--font-size-sm);
		color: var(--color-text-faint);
	}

	.chart-card {
		padding: var(--space-6);
		background: var(--color-bg-card);
		border: 1px solid var(--color-border);
		border-radius: var(--radius-lg);
	}

	.status-text {
		color: var(--color-text-dim);
		font-size: var(--font-size-lg);
	}

	.engine-down {
		display: flex;
		flex-direction: column;
		align-items: flex-start;
		gap: var(--space-3);
		max-width: 40ch;
		padding: var(--space-6);
		background: var(--color-bg-card);
		border: 1px solid var(--color-danger);
		border-radius: var(--radius-md);
	}

	.engine-down-title {
		font-size: var(--font-size-lg);
		font-weight: 700;
		color: var(--color-danger);
	}

	.engine-down-detail {
		font-size: var(--font-size-sm);
		color: var(--color-text-dim);
	}

	.retry-button {
		padding: var(--space-2) var(--space-5);
		background: transparent;
		border: 1px solid var(--color-border-strong);
		border-radius: var(--radius-sm);
		color: var(--color-text);
		font-size: var(--font-size-sm);
		font-weight: 600;
		cursor: pointer;
	}

	.retry-button:hover {
		background: var(--color-bg-card-hover);
	}

	.retry-button:focus-visible {
		outline: 2px solid var(--color-accent);
		outline-offset: 2px;
	}
</style>
