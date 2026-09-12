<script lang="ts">
	import { onMount } from 'svelte';
	import { scenarioStore } from '$lib/scenario.svelte';
	import { formatCurrency, formatPercent } from '$lib/format';
	import HeroCard from '$lib/components/HeroCard.svelte';
	import MetricRow from '$lib/components/MetricRow.svelte';

	// Today renders the shared store: the healthy baseline on a fresh load,
	// the shocked state once the shock is inserted from the Future screen.
	// It never owns its own request.
	onMount(() => {
		scenarioStore.ensureLoaded();
	});
</script>

<svelte:head>
	<title>Ginseng — Today</title>
</svelte:head>

{#if scenarioStore.loadState === 'loading'}
	<p class="status-text" role="status" aria-live="polite">Loading your liquidity picture…</p>
{:else if scenarioStore.loadState === 'unreachable' || scenarioStore.loadState === 'error'}
	<div class="engine-down" role="alert">
		<p class="engine-down-title">Engine unavailable</p>
		<p class="engine-down-detail">
			{scenarioStore.errorMessage}
		</p>
		<button class="retry-button" onclick={() => scenarioStore.refresh()}>Retry</button>
	</div>
{:else if scenarioStore.response}
	{@const s = scenarioStore.response}
	<div class="today-screen">
		<HeroCard
			eyebrow={s.funding_gap > 0 ? 'Additional funding required' : 'Funding fully covered'}
			value={formatCurrency(s.funding_gap)}
			supporting={`to maintain your ${formatCurrency(s.operating_buffer)} operating buffer in ${formatPercent(s.coverage_target)} of modeled paths`}
			estimateRangeLabel={s.estimate_band ? 'Model-estimate range' : undefined}
			estimateRangeValue={s.estimate_band
				? `${formatCurrency(s.estimate_band.low)} – ${formatCurrency(s.estimate_band.high)}`
				: undefined}
		/>

		<section class="tier" aria-label="Severity">
			<h2 class="tier-label">If this happens</h2>
			<MetricRow
				label="Cash-shortfall probability"
				value={formatPercent(s.severity.cash_shortfall_probability)}
				tone={s.severity.cash_shortfall_probability > 0 ? 'warning' : 'neutral'}
			/>
			<MetricRow
				label="Average cash deficit when short"
				value={formatCurrency(s.severity.avg_cash_deficit_when_short)}
				tone={s.severity.avg_cash_deficit_when_short > 0 ? 'warning' : 'neutral'}
			/>
		</section>

		<section class="tier" aria-label="Available capital">
			<h2 class="tier-label">What you have</h2>
			<MetricRow label="Immediate funding" value={formatCurrency(s.immediate_funding)} />
			<MetricRow
				label="Marketable backup capital"
				value={formatCurrency(s.marketable_backup_capital)}
			/>
		</section>
	</div>
{/if}

<style>
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

	.today-screen {
		display: flex;
		flex-direction: column;
		gap: var(--space-6);
	}

	.tier {
		padding: var(--space-2) var(--space-6);
		background: var(--color-bg-card);
		border: 1px solid var(--color-border);
		border-radius: var(--radius-md);
	}

	.tier-label {
		padding-top: var(--space-3);
		font-size: var(--font-size-xs);
		font-weight: 600;
		letter-spacing: 0.08em;
		text-transform: uppercase;
		color: var(--color-text-faint);
	}
</style>
