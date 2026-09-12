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
	<title>Ginseng — Plans</title>
</svelte:head>

{#if scenarioStore.response}
	{@const s = scenarioStore.response}
	{@const baseline = scenarioStore.baselineResponse}
	<div class="plans-screen">
		<header class="screen-header">
			<h1 class="screen-title">Plans</h1>
			<p class="screen-subtitle">Funding alternatives and the recommendation under your policy.</p>
		</header>

		<section class="plan-table-section" aria-label="Funding plan comparison">
			<PlanTable plans={s.plans} recommendation={s.recommendation} />
		</section>

		<section class="frozen-portfolio" aria-label="Frozen portfolio contrast">
			<h2 class="tier-label">The portfolio, before and after</h2>
			{#if baseline}
				<div class="contrast-table-wrap">
					<table class="contrast-table">
						<thead>
							<tr>
								<th scope="col" class="row-header-col">Quantity</th>
								<th scope="col">Before shock</th>
								<th scope="col">After shock</th>
							</tr>
						</thead>
						<tbody>
							<tr>
								<th scope="row" class="row-header-col">Portfolio value (marketable holdings)</th>
								<td>{formatCurrency(baseline.marketable_backup_capital)}</td>
								<td>{formatCurrency(s.marketable_backup_capital)}</td>
							</tr>
							<tr>
								<th scope="row" class="row-header-col">Portfolio volatility</th>
								<td class="muted-cell" colspan="2">Not modeled in this build</td>
							</tr>
							<tr class="risen-row">
								<th scope="row" class="row-header-col">Required funding</th>
								<td>{formatCurrency(baseline.required_liquidity_reserve)}</td>
								<td class="risen">{formatCurrency(s.required_liquidity_reserve)}</td>
							</tr>
							<tr class="risen-row">
								<th scope="row" class="row-header-col">Cash-shortfall probability</th>
								<td>{formatPercent(baseline.severity.cash_shortfall_probability)}</td>
								<td class="risen">{formatPercent(s.severity.cash_shortfall_probability)}</td>
							</tr>
						</tbody>
					</table>
				</div>
			{:else}
				<p class="muted-cell">Baseline comparison unavailable right now.</p>
			{/if}

			<p class="demo-line">The market didn't change. The person did.</p>
		</section>
	</div>
{:else if scenarioStore.loadState === 'unreachable' || scenarioStore.loadState === 'error'}
	<div class="engine-down" role="alert">
		<p class="engine-down-title">Engine unavailable</p>
		<p class="engine-down-detail">{scenarioStore.errorMessage}</p>
		<button type="button" class="retry-button" onclick={() => scenarioStore.refresh()}>Retry</button>
	</div>
{:else}
	<p class="status-text" role="status" aria-live="polite">Loading your funding plans…</p>
{/if}

<style>
	.plans-screen {
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

	.frozen-portfolio {
		display: flex;
		flex-direction: column;
		gap: var(--space-4);
		padding: var(--space-6);
		background: var(--color-bg-card);
		border: 1px solid var(--color-border);
		border-radius: var(--radius-lg);
	}

	.tier-label {
		font-size: var(--font-size-xs);
		font-weight: 600;
		letter-spacing: 0.08em;
		text-transform: uppercase;
		color: var(--color-text-faint);
	}

	.contrast-table-wrap {
		overflow-x: auto;
	}

	.contrast-table {
		width: 100%;
		border-collapse: collapse;
		font-size: var(--font-size-sm);
	}

	.contrast-table th,
	.contrast-table td {
		padding: var(--space-3) var(--space-4);
		text-align: right;
		border-bottom: 1px solid var(--color-border);
		font-variant-numeric: tabular-nums;
	}

	.contrast-table thead th {
		text-align: right;
		color: var(--color-text-faint);
		font-size: var(--font-size-xs);
		text-transform: uppercase;
		letter-spacing: 0.06em;
		font-weight: 600;
	}

	.contrast-table tbody tr:last-child th,
	.contrast-table tbody tr:last-child td {
		border-bottom: none;
	}

	.row-header-col {
		text-align: left;
		color: var(--color-text-dim);
		font-weight: 500;
	}

	.risen {
		color: var(--color-warning);
		font-weight: 700;
	}

	.muted-cell {
		color: var(--color-text-faint);
		text-align: left;
	}

	.demo-line {
		font-size: var(--font-size-lg);
		font-weight: 700;
		font-style: italic;
		color: var(--color-accent-strong);
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
